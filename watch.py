#!/usr/bin/env python3
"""Watchlist report: how the niches you are testing move, day by day.

    python watch.py                 # latest run vs ~a week earlier -> reports/watch_<run>.md + .csv

For every niche in watchlist.txt: listings, sellers and units now vs the comparison run, then its
top listings with the net change of Daraz's sold count per week (it looks like a rolling window,
so this is acceleration: new sales minus sales leaving the window) and price changes. Compares against the newest run at least
6 days older (else the oldest earlier run) -- Daraz rounds "2.7K sold", so day-to-day deltas are noise.
Uses every crawled page of the niche (the pipeline crawls watchlist niches deep every day).
"""
import datetime
import os

import pandas as pd

from analyze import latest_run
from daraz import db

TOP = 15


def read_list(path="watchlist.txt"):
    with open(path) as f:
        return [s.strip() for s in f if s.strip() and not s.lstrip().startswith("#")]


def movers(now, before, days):
    """now/before: [{nid, name, sold, price, seller}] -> per-listing change, scaled to a week."""
    prev = {r["nid"]: r for r in before}
    out = []
    for r in now:
        p = prev.get(r["nid"])
        out.append({**r, "new": p is None,
                    # Daraz's count can turn 0 (hidden), which is not a fall
                    "per_week": (round((r["sold"] - p["sold"]) * 7 / max(days, 1))
                                 if p and not (r["sold"] == 0 and p["sold"] > 0) else None),
                    "price_change": (r["price"] - p["price"]) if p else None})
    return sorted(out, key=lambda r: -r["sold"])


def compare_run(con, run):
    day = datetime.date.fromisoformat(run[:10])
    runs = [r for (r,) in con.execute("SELECT DISTINCT run_id FROM crawl_log WHERE run_id < ? ORDER BY run_id",
                                      (run,))]
    old = [r for r in runs if datetime.date.fromisoformat(r[:10]) <= day - datetime.timedelta(days=6)]
    return (old[-1] if old else (runs[0] if runs else None))


def listings(con, run, cat):
    q = ("SELECT nid, name, sold_count AS sold, price, COALESCE(seller_name, seller_id) AS seller, "
         "json_extract(raw_json, '$._page') FROM products WHERE scraped_at = ? AND category = ?")
    return [dict(zip(("nid", "name", "sold", "price", "seller", "page"), r)) for r in con.execute(q, (run, cat))]


def niche_change(now, before):
    """Like-for-like niche figures: runs can crawl a niche to different depths, so counts use page 1
    of both runs and the unit change only listings present in both."""
    p1, p1b = [r for r in now if r.get("page") == 1], [r for r in before if r.get("page") == 1]
    prev = {r["nid"]: r["sold"] for r in before}
    return {"listings_p1": len(p1), "sellers_p1": len({r["seller"] for r in p1}),
            "sellers_p1_change": len({r["seller"] for r in p1}) - len({r["seller"] for r in p1b}),
            "new_on_p1": sum(r["nid"] not in prev for r in p1) if before else 0,
            "units_change_matched": sum(r["sold"] - prev[r["nid"]] for r in now if r["nid"] in prev)}


def main():
    con = db.connect_ro()
    run = latest_run(con)
    base = compare_run(con, run)
    days = ((datetime.date.fromisoformat(run[:10]) - datetime.date.fromisoformat(base[:10])).days
            if base else 0)
    md = [f"# Watchlist — {run}", "",
          f"Compared with `{base}` ({days} days earlier); per-week figures are scaled to 7 days."
          if base else "No earlier run yet: this is the baseline. Changes appear from the next run on.", ""]
    rows = []
    for cat in read_list():
        now, before = listings(con, run, cat), listings(con, base, cat) if base else []
        if not now:
            md += [f"## {cat}", "", "Not crawled in this run.", ""]
            continue
        ms = movers(now, before, days) if base else movers(now, [], 1)
        c = niche_change(now, before)
        head = (f"Page 1: {c['listings_p1']} listings · {c['sellers_p1']} sellers · {len(now)} listings crawled in all"
                + (f" · Δ {c['units_change_matched']:+,} units on listings in both runs, "
                   f"{c['sellers_p1_change']:+d} sellers and {c['new_on_p1']} new listings on page 1" if base else ""))
        md += [f"## {cat}", "", head, "", "| Listing | Price | Sold | / week | Price Δ | Seller |",
               "|---|--:|--:|--:|--:|---|"]
        for r in ms[:TOP]:
            wk = "new" if r["new"] and base else ("—" if r["per_week"] is None else f"{r['per_week']:+,}")
            pc = "" if r["price_change"] in (None, 0) else f"{r['price_change']:+,.0f}"
            name = " ".join(str(r["name"]).split()).replace("|", "/")[:60]
            md.append(f"| {name} | {r['price']:,.0f} | {r['sold']:,} | {wk} | {pc} | {r['seller'] or ''} |")
            rows.append({"run": run, "base": base, "category": cat, **{k: r[k] for k in
                         ("nid", "name", "price", "sold", "per_week", "price_change", "new", "seller")}})
        md.append("")
    con.close()
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/watch_{run}.md", "w") as f:
        f.write("\n".join(md) + "\n")
    pd.DataFrame(rows).to_csv(f"reports/watch_{run}.csv", index=False)
    print(f"wrote reports/watch_{run}.md (+ .csv), base {base}")


if __name__ == "__main__":
    main()
