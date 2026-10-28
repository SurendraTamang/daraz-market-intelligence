#!/usr/bin/env python3
"""Export the market-entry dashboard datasets (JSON row files) from the latest run.

    python export_dashboard.py            # -> dashboard/*.json

coverage.json  one row: run, categories crawled/live/dead/empty, products, niches
niches.json    top 50 niches, ranked on page 1 (fair); stats from every crawled page
products.json  top 5 products of each of those niches + top 150 overall (overall_rank = page-1 rank)
price_bands.json  units sold by price band, page 1 of every category
"""
import json
import os

from analyze import latest_run, load_rows, niches, score_rows
from daraz import db

OUT = "dashboard"
TOP_NICHES = 50
BANDS = [(0, 200, "< Rs 200"), (200, 500, "Rs 200–500"), (500, 1000, "Rs 500–1k"),
         (1000, 2500, "Rs 1k–2.5k"), (2500, 5000, "Rs 2.5k–5k"), (5000, 10**12, "Rs 5k+")]


def label(slug):
    return slug.replace("%c3%a9", "é").replace("-", " ").strip().capitalize()


def link(url):
    return "https:" + url if url and url.startswith("//") else (url or "")


def main():
    con = db.connect_ro()
    run = latest_run(con)
    products = score_rows(load_rows(con))                       # page 1: ranking
    deep = {n["category"]: n for n in niches(score_rows(load_rows(con, max_page=None)))}
    status = dict(con.execute(
        "SELECT status, COUNT(DISTINCT category) FROM crawl_log WHERE run_id = ? AND page = 1 "
        "GROUP BY status", (run,)).fetchall())
    pages = {c: (mx, miss or 0) for c, mx, miss in con.execute(
        "SELECT category, MAX(page) FILTER (WHERE status = 'ok'), "
        "SUM(status IN ('stale', 'error', 'blocked')) FROM crawl_log WHERE run_id = ? GROUP BY category",
        (run,))}
    con.close()
    ns = niches(products)

    niche_rows, product_rows = [], {}
    for rank, n in enumerate(ns[:TOP_NICHES], 1):
        c = n["category"]
        k, miss = pages.get(c, (1, 0))
        d = deep[c] if (k or 1) > 1 and c in deep else n       # brief stats: all crawled pages
        niche_rows.append({
            "rank": rank, "niche": c, "name": label(c), "score": n["score"],
            "units": d["units"], "sellers": d["sellers"], "top_seller_share": round(d["top1_share"], 4),
            "price_p25": d["price_p25"], "price_median": d["price_median"], "price_p75": d["price_p75"],
            "avg_rating": round(d["avg_rating"], 2) if d["avg_rating"] else None,
            "products": d["products"], "pages_crawled": k or 1, "pages_missing": miss,
            "url": f"https://www.daraz.com.np/{c}/",
        })
        for p in d["top"]:
            product_rows[p["nid"]] = p
    for p in products[:150]:
        product_rows.setdefault(p["nid"], p)

    overall = {p["nid"]: i for i, p in enumerate(products, 1)}  # page-1 rank (one scale)
    rows = [{
        "nid": p["nid"], "name": " ".join((p["name"] or "").split()), "niche": p["category"],
        "price": p["price"], "sold": p["sold_count"],
        "rating": round(p["rating"], 2) if p["rating"] else None,
        "reviews": p["review_count"] or 0, "seller": p["seller_name"] or "",
        "overall_rank": overall.get(p["nid"]), "url": link(p["url"]),
    } for p in product_rows.values()]
    rows.sort(key=lambda r: (r["overall_rank"] is None, r["overall_rank"] or 0, -r["sold"]))

    bands = []
    for lo, hi, name in BANDS:
        inb = [p for p in products if lo <= p["price"] < hi]
        bands.append({"band": name, "units": sum(p["sold_count"] for p in inb), "products": len(inb)})

    coverage = [{
        "run": run, "categories": sum(status.values()), "live": status.get("ok", 0),
        "dead": status.get("not_found", 0) + status.get("moved", 0), "empty": status.get("empty", 0),
        "products_with_sales": len(products), "niches": len(ns),
        "deepened": sum(1 for r in niche_rows if r["pages_crawled"] > 1),
    }]

    os.makedirs(OUT, exist_ok=True)
    for name, data in (("coverage", coverage), ("niches", niche_rows),
                       ("products", rows), ("price_bands", bands)):
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT}/: {len(niche_rows)} niches, {len(rows)} products, run {run}")


if __name__ == "__main__":
    main()
