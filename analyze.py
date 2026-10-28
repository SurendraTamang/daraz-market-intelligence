#!/usr/bin/env python3
"""The one Opportunity Score. Used by export_json.py, api.py, app.py, opportunity.py, brief.py.

Levers (0..1, higher = better for a new seller), all over products_dedup of the latest run:
  demand      percentile of Daraz's sold count (a rolling recent window, it seems)
  velocity    percentile of units/week vs the previous run (weight 0 until 2 runs exist)
  competition 1 - top seller's share of units in the niche (leaf category)
  quality     rating gap (4.9 - rating)/1.4, only with >= MIN_REVIEWS reviews, else neutral .5
  afford      1 - percentile of price
  generic     1 if no brand (sourceable / rebrandable)
score = weighted mean * (0.4 + 0.6 * demand)  -- demand gate: no demand, no top rank.
"""
import bisect
from collections import defaultdict

from daraz import db

WEIGHTS = {"demand": 0.30, "velocity": 0.20, "competition": 0.20,
           "quality": 0.10, "afford": 0.10, "generic": 0.10}
MIN_REVIEWS = 10
MIN_VELOCITY_DAYS = 6  # shorter windows are mostly Daraz's "2.7K sold" rounding noise: no velocity yet
PAYLOAD_TOP = 5000  # ponytail: dashboard ships top-N products; raise if the frontend needs more


def pct_rank(vals):
    """value -> mid-rank row percentile 0..1 (ties share the middle of their block)."""
    order = sorted(vals)
    n = len(order)
    if n <= 1:
        return {v: 0.5 for v in vals}
    return {v: (bisect.bisect_left(order, v) + bisect.bisect_right(order, v) - 1) / 2 / (n - 1)
            for v in set(vals)}


def is_generic(brand):
    return (brand or "").strip().lower() in ("no brand", "", "none")


def _seller_key(r):
    """seller_id, falling back to a per-product key so missing ids never merge distinct sellers."""
    return r.get("seller_id") or f"nid:{r['nid']}"


def latest_run(con):
    """The run to score: the newest crawl covering >= 90% of the best run's categories, so daily
    runs advance the dashboard but a partial (shortlist-only) run never shrinks it. Before any crawl_log exists: newest snapshot."""
    return con.execute("""
        SELECT COALESCE(
            (WITH c AS (SELECT run_id, COUNT(DISTINCT category) AS n FROM crawl_log
                        WHERE status IN ('ok', 'empty') GROUP BY run_id)
             SELECT run_id FROM c WHERE n >= 0.9 * (SELECT MAX(n) FROM c)
             ORDER BY run_id DESC LIMIT 1),
            (SELECT MAX(scraped_at) FROM products))
    """).fetchone()[0]


RANK_DEPTH = 1  # rank on listing page 1 only, so every category is compared at equal depth


def load_rows(con, max_page=RANK_DEPTH):
    """Latest run, one row per product (leaf category), only products with price and sales.

    max_page: keep only products found on listing pages <= max_page (tag `_page` in raw_json).
    Categories get crawled to different depths (deeper = more products = looks bigger), so
    ranking compares page 1 everywhere. Runs with no page tags at all (legacy) are kept whole.
    None = no depth filter."""
    run = latest_run(con)
    if max_page is not None and not con.execute(
            "SELECT 1 FROM products WHERE scraped_at = ? AND json_extract(raw_json, '$._page') "
            "IS NOT NULL LIMIT 1", (run,)).fetchone():
        max_page = None
    depth = "AND json_extract(d.raw_json, '$._page') <= ?" if max_page is not None else ""
    cols = ("nid", "name", "category", "price", "original_price", "discount", "sold_count",
            "est_revenue", "rating", "review_count", "brand", "seller_id", "seller_name",
            "location", "url", "units_per_week")
    rows = con.execute("""
        SELECT d.nid, d.name, d.category, d.price, d.original_price, d.discount, d.sold_count,
               d.est_revenue, d.rating, d.review_count, d.brand, d.seller_id, d.seller_name,
               d.location, json_extract(d.raw_json, '$.itemUrl'), v.units_per_week
        FROM products_dedup d
        LEFT JOIN velocity v ON v.nid = d.nid AND v.is_new = 0 AND v.days_between >= ?
        WHERE d.scraped_at = ? AND d.price > 0 AND d.sold_count > 0 {depth}
    """.format(depth=depth), (MIN_VELOCITY_DAYS, run) + ((max_page,) if max_page is not None else ())).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _top1_share(rows):
    by_cat = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_cat[r["category"]][_seller_key(r)] += r["sold_count"]
    return {c: max(s.values()) / (sum(s.values()) or 1) for c, s in by_cat.items()}


def score_rows(rows, weights=None):
    w = dict(weights or WEIGHTS)
    if not any(r.get("units_per_week") is not None for r in rows):
        w["velocity"] = 0.0  # no history yet: redistribute (weighted mean over the rest)
    total_w = sum(w.values()) or 1.0
    top1 = _top1_share(rows)
    dP = pct_rank([r["sold_count"] for r in rows])
    aP = pct_rank([r["price"] for r in rows])
    # negative units_per_week is noise from rounded "2.7K sold" display deltas, not real decline
    vP = pct_rank([max(0.0, r["units_per_week"]) for r in rows if r.get("units_per_week") is not None])
    out = []
    for r in rows:
        rating, reviews, upw = r.get("rating") or 0, r.get("review_count") or 0, r.get("units_per_week")
        upw = None if upw is None else max(0.0, upw)
        lv = {
            "demand": dP[r["sold_count"]],
            "velocity": vP[upw] if upw is not None else 0.5,
            "competition": 1 - top1[r["category"]],
            "quality": min(1.0, max(0.0, (4.9 - rating) / 1.4)) if reviews >= MIN_REVIEWS and rating else 0.5,
            "afford": 1 - aP[r["price"]],
            "generic": 1.0 if is_generic(r.get("brand")) else 0.0,
        }
        base = sum(w[k] * lv[k] for k in w) / total_w
        r["generic"] = bool(lv["generic"])
        r["levers"] = {k: round(v, 3) for k, v in lv.items()}
        r["score"] = round(base * (0.4 + 0.6 * lv["demand"]), 4)
        out.append(r)
    out.sort(key=lambda p: -p["score"])
    return out


def _q(sorted_vals, f):
    return sorted_vals[int(f * (len(sorted_vals) - 1))]


def niches(products, top=20):
    """One entry per leaf category. Niche score = units-weighted mean of its top-`top` product scores."""
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)
    out = []
    for cat, ps in by_cat.items():
        ps = sorted(ps, key=lambda p: -p["score"])
        best = ps[:top]
        units = sum(p["sold_count"] for p in ps)
        seller_units = defaultdict(int)
        for p in ps:
            seller_units[_seller_key(p)] += p["sold_count"]
        prices = sorted(p["price"] for p in ps)
        reviewed = [p["rating"] for p in ps if (p["review_count"] or 0) >= MIN_REVIEWS and p["rating"]]
        upw = [p["units_per_week"] for p in ps if p.get("units_per_week") is not None]
        out.append({
            "category": cat,
            "score": round(sum(p["score"] * p["sold_count"] for p in best)
                           / (sum(p["sold_count"] for p in best) or 1), 4),
            "units": units, "products": len(ps), "sellers": len(seller_units),
            "top1_share": max(seller_units.values()) / (units or 1),
            "price_p25": _q(prices, 0.25), "price_median": _q(prices, 0.5), "price_p75": _q(prices, 0.75),
            "avg_rating": sum(reviewed) / len(reviewed) if reviewed else None,
            "low_review_products": sum(1 for p in ps if (p["review_count"] or 0) < MIN_REVIEWS),
            "generic_share": sum(p["sold_count"] for p in ps if p["generic"]) / (units or 1),
            "units_per_week": sum(upw) if upw else None,
            "top": ps[:5],
        })
    out.sort(key=lambda n: -n["score"])
    return out


def build_payload(db_path=None):
    """Dashboard payload (shape = frontend/src/types.ts).

    meta/categories are rolled up over every scored row (not just the PAYLOAD_TOP slice shipped
    to the frontend) so the totals stay accurate at 2M-row scale; only the per-product frontend
    dicts are built for the capped slice, to avoid materializing a second full-size list.
    """
    con = db.connect_ro(db_path)
    products = score_rows(load_rows(con))
    con.close()

    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)

    categories = []
    for cat, ps in by_cat.items():
        units = sum(p["sold_count"] for p in ps)
        revenue = sum(round(p["est_revenue"] or 0) for p in ps)
        sellers = {_seller_key(p) for p in ps}
        categories.append({
            "category": cat, "revenue": revenue, "units": units,
            "products": len(ps), "sellers": len(sellers),
            "avgPrice": round(sum(p["price"] for p in ps) / len(ps)),
            "genericShare": round(100 * sum(p["sold_count"] for p in ps if p["generic"]) / (units or 1)),
        })
    categories.sort(key=lambda c: -c["revenue"])

    out = [{
        "name": p["name"], "category": p["category"], "price": p["price"],
        "originalPrice": p["original_price"], "discount": p["discount"], "sold": p["sold_count"],
        "revenue": round(p["est_revenue"] or 0), "rating": round(p["rating"] or 0, 2),
        "reviews": p["review_count"] or 0, "brand": p["brand"] or "No Brand", "generic": p["generic"],
        "seller": p["seller_name"], "location": p["location"] or "", "score": p["score"],
        "levers": p["levers"],
    } for p in products[:PAYLOAD_TOP]]

    return {
        "meta": {"products": len(products), "units": sum(p["sold_count"] for p in products),
                 "revenue": sum(round(p["est_revenue"] or 0) for p in products),
                 "sellers": len({_seller_key(p) for p in products}), "categories": len(categories)},
        "categories": categories,
        "products": out,
    }
