import pytest

from analytics.analyze import niches, pct_rank, score_rows


def row(nid, cat="tea", seller="s1", sold=100, price=500.0, rating=None, reviews=0,
        brand="No Brand", upw=None):
    return {"nid": nid, "name": f"item {nid}", "category": cat, "price": price, "sold_count": sold,
            "est_revenue": price * sold, "rating": rating, "review_count": reviews, "brand": brand,
            "seller_id": seller, "seller_name": seller, "location": "", "original_price": None,
            "discount": None, "url": f"//www.daraz.com.np/{nid}.html", "units_per_week": upw}


def by_nid(products):
    return {p["nid"]: p for p in products}


def test_quality_neutral_below_min_reviews():
    by = by_nid(score_rows([row("a", rating=3.0, reviews=5), row("b", rating=3.0, reviews=20)]))
    assert by["a"]["levers"]["quality"] == 0.5
    assert by["b"]["levers"]["quality"] == 1.0


def test_velocity_weight_zero_without_history():
    [p] = score_rows([row("a")])
    # D=.5 A=.5 Q=.5 C=0 (one seller owns the niche) G=1; velocity dropped -> weights sum .80
    expected = (0.30 * 0.5 + 0.20 * 0 + 0.10 * 0.5 + 0.10 * 0.5 + 0.10 * 1) / 0.80 * (0.4 + 0.6 * 0.5)
    assert p["score"] == pytest.approx(expected, abs=1e-4)


def test_competition_is_one_minus_top_seller_share():
    by = by_nid(score_rows([row("a", seller="big", sold=90), row("b", seller="small", sold=10)]))
    assert by["a"]["levers"]["competition"] == pytest.approx(0.1)


def test_scores_bounded():
    rows = [row(str(i), cat=f"c{i % 3}", seller=f"s{i % 5}", sold=i * 7 + 1, price=100 + i,
                rating=3 + i % 2, reviews=i, upw=(i if i % 2 else None)) for i in range(30)]
    assert all(0 <= p["score"] <= 1 for p in score_rows(rows))


def test_niches():
    ps = score_rows([row("a", seller="x", sold=90, price=100), row("b", seller="y", sold=10, price=300, brand="Lipton"),
                     row("c", cat="mugs", sold=5)])
    tea = {n["category"]: n for n in niches(ps)}["tea"]
    assert (tea["units"], tea["sellers"], tea["products"]) == (100, 2, 2)
    assert tea["top1_share"] == pytest.approx(0.9)
    assert tea["generic_share"] == pytest.approx(0.9)
    assert tea["price_median"] == 100
    assert len(tea["top"]) == 2
    assert tea["units_per_week"] is None


def test_pct_rank_is_tie_aware():
    vals = [1] * 8 + [5, 9]
    p = pct_rank(vals)
    assert p[1] == pytest.approx(3.5 / 9)
    assert p[5] == pytest.approx(8 / 9)
    assert p[9] == 1.0
    assert pct_rank([4, 4, 4, 4]) == {4: 0.5}


def test_velocity_clamped_at_zero():
    by = by_nid(score_rows([row("a", upw=-50), row("b", upw=0)]))
    assert by["a"]["levers"]["velocity"] == by["b"]["levers"]["velocity"] == 0.5


def test_missing_seller_id_not_merged():
    by = by_nid(score_rows([row("a", seller=None), row("b", seller=None)]))
    assert by["a"]["levers"]["competition"] == pytest.approx(0.5)
    assert by["b"]["levers"]["competition"] == pytest.approx(0.5)


def _db_with(rows):
    import json
    from daraz import db
    con = db.connect(":memory:")
    for nid, page in rows:
        raw = json.dumps({"itemUrl": f"//x/{nid}", **({"_page": page} if page else {})})
        con.execute("INSERT INTO products (nid, name, price, category, sold_count, scraped_at, raw_json, seller_id) "
                    "VALUES (?,?,?,?,?,?,?,?)", (nid, nid, 100.0, "tea", 5, "2026-10-12", raw, "s"))
    con.execute("INSERT INTO crawl_log (run_id, category, page, status, items) VALUES ('2026-10-12','tea',1,'ok',40)")
    return con


def test_load_rows_ranks_on_page1_when_pages_are_tagged():
    from analytics.analyze import load_rows
    con = _db_with([("a", 1), ("b", 2), ("c", None)])   # c: untagged deep row from before tagging
    assert {r["nid"] for r in load_rows(con)} == {"a"}
    assert {r["nid"] for r in load_rows(con, max_page=None)} == {"a", "b", "c"}


def test_load_rows_without_tags_keeps_everything():
    from analytics.analyze import load_rows
    con = _db_with([("a", None), ("b", None)])           # legacy run: no page tags at all
    assert {r["nid"] for r in load_rows(con)} == {"a", "b"}


def test_velocity_ignored_until_comparison_spans_six_days():
    from analytics.analyze import load_rows
    con = _db_with([("a", 1)])                       # run 2026-10-12, tagged page 1
    con.execute("INSERT INTO crawl_log (run_id, category, page, status, items) VALUES ('2026-10-10','tea',1,'ok',40)")
    con.execute("INSERT INTO products (nid, name, price, category, sold_count, scraped_at, raw_json, seller_id) "
                "VALUES ('a','a',100.0,'tea',3,'2026-10-10','{\"_page\":1}','s')")
    assert load_rows(con)[0]["units_per_week"] is None   # 2-day window: rounding noise, not velocity
