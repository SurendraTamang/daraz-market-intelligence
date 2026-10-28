import json

from daraz.crawl import (
    hole_targets,
    is_error_page,
    block_rate_exceeded,
    is_block_redirect,
    is_stale,
    parse_listing,
    resume_targets,
    should_follow,
    sold_items,
)

LISTING = json.dumps({
    "mainInfo": {"totalResults": "4080", "noMorePages": False},
    "mods": {"listItems": [{"nid": "1", "itemSoldCntShow": "39 sold"}, {"nid": "2"}]},
})


def test_should_follow():
    assert should_follow(1, 1, False, 3)
    assert not should_follow(1, 0, False, 3)   # page had no sold items -> stop
    assert not should_follow(1, 5, True, 3)    # Daraz says this is the last page
    assert not should_follow(3, 5, False, 3)   # budget cap reached


def test_parse_listing():
    assert parse_listing(LISTING)["mods"]["listItems"][0]["nid"] == "1"
    wrapped = "<pre>" + LISTING.replace('"', "&quot;") + "</pre>"   # MrScraper wrapper
    assert parse_listing(wrapped) is not None
    assert parse_listing("<html><body>punish captcha</body></html>") is None
    assert parse_listing("") is None
    assert parse_listing('{"ok": true}') is None   # JSON, but not a listing
    assert parse_listing("null") is None
    assert parse_listing('["mods"]') is None
    assert parse_listing('{"mods": null}') is None


def test_sold_items():
    assert sold_items(json.loads(LISTING)["mods"]["listItems"]) == 1


def test_block_rate_exceeded():
    assert not block_rate_exceeded([True] * 49)                   # too few samples to judge
    assert block_rate_exceeded([True] * 13 + [False] * 37)        # 50 samples, 26% -> exceeds
    assert not block_rate_exceeded([True] * 10 + [False] * 40)    # 50 samples, exactly 20% is not > 20%


def test_is_block_redirect():
    assert is_block_redirect("https://www.daraz.com.np/punish/xyz")
    assert is_block_redirect("https://www.daraz.com.np/CAPTCHA/abc")   # case-insensitive
    assert is_block_redirect("https://www.daraz.com.np/x5sec?foo=bar")
    assert is_block_redirect("https://login.daraz.com.np/?redirect=/")
    assert is_block_redirect("https://www.daraz.com.np/verify-human")
    assert not is_block_redirect("https://www.daraz.com.np/new-category-slug/")
    assert not is_block_redirect(None)
    assert not is_block_redirect("")


def test_resume_targets():
    # (category, page, status, items, sold_items, no_more_pages)
    log = [
        ("a", 1, "ok", 40, 10, 0), ("a", 2, "ok", 40, 3, 0),
        ("b", 1, "ok", 40, 0, 0),
        ("c", 1, "ok", 40, 5, 0), ("c", 2, "blocked", None, None, None),
    ]
    assert resume_targets(["a", "b", "c", "d"], log, 3) == [("a", 3), ("c", 2), ("d", 1)]
    assert resume_targets(["a"], log, 2) == []


def test_resume_targets_edge_cases():
    # (category, page, status, items, sold_items, no_more_pages)
    log = [
        ("e", 1, "empty", 40, 0, 0),           # deepest page is "empty" with 0 sold -> stop
        ("f", 1, "ok", 40, 5, 1),               # deepest ok page says no_more_pages -> stop
        ("g", 2, "ok", 40, 7, 0), ("g", 1, "ok", 40, 3, 0),  # out of order -> resume from page 2
        ("h", 1, "ok", 40, None, 0),            # sold_items None -> treated as 0 -> stop
    ]
    assert resume_targets(["e", "f", "g", "h"], log, 3) == [("g", 3)]


def test_resume_targets_terminal_statuses():
    # (category, page, status, items, sold_items, no_more_pages)
    log = [
        ("dead", 1, "not_found", None, None, None),    # 404 at page 1 -> terminal, no restart
        ("renamed", 1, "moved", None, None, None),      # 301 (non-block) -> terminal, no restart
        ("alive", 1, "ok", 40, 5, 0),
    ]
    assert resume_targets(["dead", "renamed", "alive", "fresh"], log, 3) == [("alive", 2), ("fresh", 1)]


def test_resume_targets_terminal_status_wins_even_with_later_ok_row():
    # a category marked terminal must never resume, even if other rows for it look resumable
    log = [
        ("a", 1, "not_found", None, None, None),
        ("a", 2, "ok", 40, 5, 0),
    ]
    assert resume_targets(["a"], log, 3) == []


def test_resume_targets_stale_is_non_terminal_and_resumes_at_the_stale_page():
    # "stale" (previous page served again) must behave like "error": not terminal, and not
    # counted as the deepest ok/empty page -- so the category resumes at the stale page
    # itself (re-fetching it), not past it.
    log = [
        ("x", 1, "ok", 40, 5, 0),
        ("x", 2, "stale", 40, 0, 0),
    ]
    assert resume_targets(["x"], log, 3) == [("x", 2)]


def test_is_stale():
    page1 = {str(i) for i in range(40)}
    assert is_stale(page1, page1)                              # identical page -> True
    assert not is_stale(page1, {str(i) for i in range(40, 80)})  # disjoint -> False
    overlap_20 = {str(i) for i in range(20)} | {str(i) for i in range(100, 120)}
    assert is_stale(page1, overlap_20)                          # 20/40 overlap -> True
    overlap_19 = {str(i) for i in range(19)} | {str(i) for i in range(100, 121)}
    assert not is_stale(page1, overlap_19)                      # 19/40 overlap -> False
    assert not is_stale(set(), page1)                           # empty prev -> False
    assert not is_stale(page1, set())                           # empty current -> False


def test_should_follow_stops_at_real_end_of_category():
    # Daraz keeps serving full (repeated) pages past the end; totalResults is the truth.
    assert should_follow(2, 5, False, 102, total_results=82)       # 80 < 82 -> page 3 exists
    assert not should_follow(3, 5, False, 102, total_results=82)   # 120 >= 82 -> stop
    assert not should_follow(2, 5, False, 102, total_results=80)   # exactly 2 full pages
    assert should_follow(2, 5, False, 102, total_results=None)     # unknown -> old rule


def test_resume_targets_uses_total_results_when_logged():
    # 7th column = total_results
    log = [("small", 2, "ok", 40, 30, 0, 80), ("big", 3, "ok", 40, 30, 0, 4080)]
    assert resume_targets(["small", "big"], log, 102) == [("big", 4)]


def test_is_error_page():
    err = '<html><head><meta name="page-url" content="https://www.daraz.com.np/wow/gcp/route/daraz/np/upr/router?wh_pid=/lazada/channel/np/common/error">'
    assert is_error_page(err)
    assert not is_error_page('{"mods": {"listItems": []}}')
    assert not is_error_page("<html>punish captcha</html>")
    assert not is_error_page(None)


def test_hole_targets_are_failed_pages_below_deepest_ok():
    log = [("a", 1, "ok", 40, 30, 0), ("a", 2, "stale", 40, 30, 0), ("a", 3, "ok", 40, 30, 0),
           ("a", 4, "error", None, None, None),                      # above deepest ok: not a hole
           ("b", 1, "ok", 40, 30, 0), ("b", 2, "blocked", None, None, None)]  # b: resume handles it
    assert hole_targets(log) == {"a": [2]}
