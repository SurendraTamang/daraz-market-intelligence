#!/usr/bin/env python3
"""Opportunity CLI: ranked "what to sell" list. Scores come from analyze.py.

    python opportunity.py --top 20
    DARAZ_DB=other.db python opportunity.py
"""
import argparse
from collections import defaultdict

from analyze import load_rows, score_rows
from daraz import db

BANDS = [(0, 300, "<300"), (300, 700, "300-700"), (700, 1500, "700-1.5k"),
         (1500, 3000, "1.5-3k"), (3000, 8000, "3-8k"), (8000, 10**12, "8k+")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    con = db.connect_ro()
    products = score_rows(load_rows(con))
    con.close()
    top = products[:a.top]

    print(f"\n{'=' * 96}\nTOP {a.top} OPPORTUNITIES\n{'=' * 96}")
    print(f"{'#':>2} {'score':>5} {'product':42} {'cat':16} {'price':>7} {'sold':>6} {'★':>4}  why")
    for i, p in enumerate(top, 1):
        lv = p["levers"]
        why = [label for key, cut, label in (
            ("demand", 0.7, "high demand"), ("velocity", 0.7, "selling fast"),
            ("afford", 0.7, "cheap to stock"), ("quality", 0.55, "weak incumbent quality"),
            ("competition", 0.6, "no dominant seller")) if lv[key] > cut]
        print(f"{i:>2} {p['score']:5.2f} {(p.get('name') or '')[:42]:42} {p['category'][:16]:16} "
              f"{int(p['price']):>7,} {p['sold_count']:>6,} {(p['rating'] or 0):>4.1f}  {', '.join(why) or '-'}")

    cats = list(dict.fromkeys(p["category"] for p in top))
    by_cat = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)
    print(f"\n{'=' * 70}\nBRAND vs GENERIC + PRICE SWEET SPOT (categories above)\n{'=' * 70}")
    for c in cats:
        ps = by_cat[c]
        units = sum(p["sold_count"] for p in ps) or 1
        g = 100 * sum(p["sold_count"] for p in ps if p["generic"]) / units
        band_units = defaultdict(int)
        for p in ps:
            band_units[next(lbl for lo, hi, lbl in BANDS if lo <= p["price"] < hi)] += p["sold_count"]
        best = max(band_units, key=band_units.get)
        print(f"{c[:24]:24} generic {g:>3.0f}%  sweet spot Rs {best:9} ({band_units[best]:,} units)")


if __name__ == "__main__":
    main()
