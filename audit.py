#!/usr/bin/env python3
"""Content audit for one crawl run. Run it before trusting any brief. Limitations print first.

    python audit.py                         # latest run, no network
    PROXY=liveproxies python audit.py --spot 5    # + live spot-check of 5 category pages
"""
import argparse
import random

from analyze import latest_run
from daraz import db, transport
from daraz.crawl import parse_listing
from daraz.utils import parse_sold_count, to_float

FIELDS = ("name", "price", "sold_count", "rating", "review_count", "seller_id", "brand", "location")


def compare_page(db_rows, live_items):
    """db_rows: {nid: (price, sold)}. Returns (checked, price_matches, sold_matches)."""
    checked = price_ok = sold_ok = 0
    for it in live_items:
        nid = str(it.get("nid"))
        if nid not in db_rows:
            continue
        checked += 1
        price, sold = db_rows[nid]
        price_ok += to_float(it.get("price")) == price
        sold_ok += parse_sold_count(it.get("itemSoldCntShow")) == sold
    return checked, price_ok, sold_ok


def empty_rates(con, run, cols):
    """One query, all columns: AVG(CASE ...) per column -> {col: rate}."""
    exprs = ", ".join(
        f"AVG(CASE WHEN {c} IS NULL OR TRIM(CAST({c} AS TEXT)) "
        f"IN ('', 'None', 'none', 'null', '0', '0.0') THEN 1.0 ELSE 0 END)" for c in cols)
    row = con.execute(f"SELECT {exprs} FROM products WHERE scraped_at = ?", (run,)).fetchone()
    return {c: (row[i] or 0.0) for i, c in enumerate(cols)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--spot", type=int, default=0)
    a = ap.parse_args()
    con = db.connect_ro()
    run = a.run or latest_run(con)
    one = lambda sql: con.execute(sql, (run,)).fetchone()[0]  # noqa: E731

    rows = one("SELECT COUNT(*) FROM products WHERE scraped_at = ?")
    nids = one("SELECT COUNT(DISTINCT nid) FROM products WHERE scraped_at = ?")
    multi = one("SELECT COUNT(*) FROM (SELECT nid FROM products WHERE scraped_at = ? "
                "GROUP BY nid HAVING COUNT(DISTINCT category) > 1)")
    status = dict(con.execute("SELECT status, COUNT(*) FROM crawl_log WHERE run_id = ? GROUP BY status",
                              (run,)).fetchall())
    pages = sum(status.values())
    bad = status.get("blocked", 0) + status.get("error", 0)
    stale = status.get("stale", 0)
    worst = con.execute("SELECT category, COUNT(*) FROM crawl_log WHERE run_id = ? AND status IN "
                        "('blocked','error') GROUP BY category ORDER BY 2 DESC LIMIT 10", (run,)).fetchall()
    no_brand = one("SELECT AVG(LOWER(COALESCE(brand,'')) IN ('no brand','')) FROM products WHERE scraped_at = ?") or 0
    pages_items = one("SELECT SUM(items) FROM crawl_log WHERE run_id = ? AND status IN ('ok','empty')") or 0
    stored = rows
    rates = empty_rates(con, run, FIELDS)

    print(f"AUDIT run {run}: {rows:,} rows, {nids:,} distinct products, {pages:,} pages logged\n")
    print("LIMITATIONS")
    print(f"  - failed pages (blocked/error): {bad:,} of {pages:,} ({bad / (pages or 1):.1%})"
          + (f" — worst: {', '.join(f'{c}({n})' for c, n in worst)}" if worst else ""))
    print(f"  - stale pages (previous page served again, after retries): {stale:,}")
    if not pages:
        print("  - no crawl_log rows: legacy run, page-level coverage unknown")
    if pages_items > 0:
        loss = 1 - stored / pages_items
        print(f"  - page duplication loss: {loss:.1%} ({stored:,} rows stored from {pages_items:,} "
              f"listed items; >5% means stale pages slipped through)")
    print(f"  - sold_count missing: {rates['sold_count']:.0%} (conditional: Daraz hides counts on low sellers)")
    print(f"  - rating missing: {rates['rating']:.0%} (conditional: products without reviews)")
    print(f"  - brand 'No Brand'/empty: {no_brand:.0%} (placeholder: some real brands are mislabelled)")
    print(f"  - products in >1 category: {multi:,} (handled by products_dedup)")
    print("\nEMPTY RATE PER FIELD ('', 'None', NULL, 0 count as empty)")
    for col in FIELDS:
        print(f"  {col:14} {rates[col]:6.1%}")
    print(f"\nSTATUS {status}")

    if a.spot:
        cats = [r[0] for r in con.execute(
            "SELECT category FROM crawl_log WHERE run_id = ? AND page = 1 AND status = 'ok'", (run,))]
        print(f"\nLIVE SPOT-CHECK ({min(a.spot, len(cats))} category page-1s via PROXY={transport.mode()})")
        for cat in random.sample(cats, min(a.spot, len(cats))):
            data = parse_listing(transport.fetch(f"https://www.daraz.com.np/{cat}/?ajax=true&page=1"))
            if data is None:
                print(f"  {cat}: BLOCKED")
                continue
            db_rows = {n: (p, s) for n, p, s in con.execute(
                "SELECT nid, price, sold_count FROM products WHERE scraped_at = ? AND category = ?", (run, cat))}
            checked, p_ok, s_ok = compare_page(db_rows, data["mods"].get("listItems", []))
            print(f"  {cat}: {checked} overlapping products, price match {p_ok}/{checked}, "
                  f"sold match {s_ok}/{checked} (sold can legitimately rise since the crawl)")
    con.close()


if __name__ == "__main__":
    main()
