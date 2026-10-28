"""Pure crawl decisions (no Scrapy, no I/O), so they're unit-testable."""
from daraz.utils import extract_json, parse_sold_count

# Keywords seen in Daraz's own block/captcha redirect targets. A redirect to a dead or
# renamed category (e.g. a 301 to a sibling slug, or Daraz's generic "not found" page) must
# NOT match any of these, or a dead category would be retried forever as if it were blocked
# instead of being logged "moved" and left alone (see resume_targets).
BLOCK_REDIRECT_KEYWORDS = ("punish", "captcha", "x5sec", "login", "verify")


def parse_listing(text):
    """Listing JSON as a dict, or None when the response is a block/captcha/non-listing page."""
    try:
        data = extract_json(text)
    except ValueError:  # json.JSONDecodeError is a ValueError
        return None
    return data if isinstance(data, dict) and isinstance(data.get("mods"), dict) else None


def is_block_redirect(location):
    """True if a redirect's Location header looks like Daraz's block/captcha page.

    location may be None/"" (no Location header) -> False, which keeps a dead/renamed
    category (just some other 30x target) from being treated as a block.
    """
    if not location:
        return False
    loc = location.lower()
    return any(kw in loc for kw in BLOCK_REDIRECT_KEYWORDS)


ERROR_PAGE_MARKER = "wh_pid=/lazada/channel/np/common/error"


def is_error_page(text):
    """Daraz's generic error page (dead/landing-only sitemap slug), served with HTTP 200.
    Not a captcha: retrying never helps, so callers treat it as not_found."""
    return bool(text) and ERROR_PAGE_MARKER in text


def sold_items(items):
    """How many listing items show a non-zero 'X sold'."""
    return sum(1 for it in items if parse_sold_count(it.get("itemSoldCntShow")) > 0)


PAGE_SIZE = 40


def should_follow(page, n_sold, no_more_pages, max_pages, total_results=None):
    """Go to page+1 only while this page still has sales, Daraz has more, and budget allows.
    totalResults is the real end: past it Daraz keeps serving full pages of repeated items
    (and doesn't set noMorePages), so page*40 >= totalResults means stop."""
    past_end = bool(total_results) and page * PAGE_SIZE >= total_results
    return n_sold > 0 and not no_more_pages and not past_end and page < max_pages


def block_rate_exceeded(window, threshold=0.2, min_samples=50):
    """window: recent booleans, True = blocked/error page."""
    return len(window) >= min_samples and sum(window) / len(window) > threshold


def is_stale(prev_nids, nids, threshold=0.5):
    """True when this page's items look like the previous page served again.

    Daraz's listing endpoint sometimes returns a stale/lagged page: mainInfo.page says N but
    the item content is page N-1's. Page content sets are consistent across Daraz's A/B
    buckets, so a high overlap with the previous page (not just any duplicate items) is the
    signal. Empty prev or empty current -> False (nothing to compare against).
    """
    if not prev_nids or not nids:
        return False
    return len(prev_nids & nids) / len(nids) >= threshold


def resume_targets(slugs, log_rows, max_pages):
    """(slug, page) requests still needed for this run.

    log_rows: (category, page, status, items, sold_items, no_more_pages[, total_results]) from
    crawl_log for the current run. Resume from each category's deepest ok/empty page; unseen categories start at 1.
    "not_found" (404/410) and "moved" (a non-block 30x, e.g. a renamed/dead category) are
    terminal: once seen for a category, that category is never requested again this run --
    not resumed deeper, and not restarted at page 1 either.
    """
    deepest = {}
    terminal = set()
    for cat, page, status, _items, n_sold, no_more, *rest in log_rows:
        if status in ("not_found", "moved"):
            terminal.add(cat)
            continue
        if status in ("ok", "empty") and page > deepest.get(cat, (0,))[0]:
            deepest[cat] = (page, n_sold or 0, bool(no_more), rest[0] if rest else None)
    out = []
    for slug in slugs:
        if slug in terminal:
            continue
        if slug not in deepest:
            out.append((slug, 1))
            continue
        page, n_sold, no_more, total = deepest[slug]
        if should_follow(page, n_sold, no_more, max_pages, total):
            out.append((slug, page + 1))
    return out


def hole_targets(log_rows):
    """{category: [pages]} of stale/error/blocked pages BELOW the category's deepest ok page.
    resume_targets only extends past the deepest ok page, so these would never be re-fetched."""
    deepest, bad = {}, {}
    for cat, page, status, *_ in log_rows:
        if status == "ok":
            deepest[cat] = max(page, deepest.get(cat, 0))
        elif status in ("stale", "error", "blocked"):
            bad.setdefault(cat, []).append(page)
    holes = {c: sorted(p for p in ps if p < deepest.get(c, 0)) for c, ps in bad.items()}
    return {c: ps for c, ps in holes.items() if ps}
