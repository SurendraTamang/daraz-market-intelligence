#!/usr/bin/env python3
"""Market-entry briefs: briefs/index.md + one page per top niche (+ briefs/shortlist.txt).

    python brief.py --top 20
    python brief.py --write-shortlist --shortlist 50     # once, after a full crawl

shortlist.txt feeds the weekly velocity crawl (CATEGORIES_FILE=briefs/shortlist.txt).
"""
import argparse
import glob
import os

from analyze import latest_run, load_rows, niches, score_rows
from daraz import db


def money(n):
    return f"Rs {n:,.0f}"


def link(url):
    return "https:" + url if url and url.startswith("//") else (url or "")


def md_text(s):
    """Collapse whitespace and neutralize Markdown table/link syntax so a product or seller
    name can never break a `|`-delimited row or a `[...](...)` link."""
    return " ".join((s or "").split()).replace("|", "/").replace("[", "(").replace("]", ")")


NOTES_CHECKLIST = ["- [ ] Sourcing cost per unit + MOQ:",
                   "- [ ] Margin ≥ 2–3× after Daraz fees + ads:",
                   "- [ ] Video / demo angle:",
                   "- [ ] Weakest incumbent to beat (link + why):"]


def notes_template(category):
    return "\n".join([f"# Notes — {category}", ""] + NOTES_CHECKLIST + [""])


def render(rank, n, run, has_velocity):
    vel = (f"{n['units_per_week']:+,.0f} net change of sold count per week (coarse above ~1K: Daraz rounds)"
           if has_velocity and n["units_per_week"] is not None else "no trend yet (needs a week of snapshots)")
    rating = (f"{n['avg_rating']:.2f}★ avg over products with ≥10 reviews" if n["avg_rating"]
              else "no product has ≥10 reviews")
    lines = [
        f"# {rank}. {n['category']}", "",
        f"Run `{run}` · niche score {n['score']:.3f} (ranked on page 1) · https://www.daraz.com.np/{n['category']}/",
        f"Data depth: {n.get('depth', 'page 1')} · {n['products']:,} products with sales", "",
        "| Signal | Value |", "|---|---|",
        f"| Units sold (Daraz count) | {n['units']:,} |",
        f"| Velocity | {vel} |",
        f"| Sellers / top seller share | {n['sellers']} / {n['top1_share']:.0%} |",
        f"| Price p25 / median / p75 | {money(n['price_p25'])} / {money(n['price_median'])} / {money(n['price_p75'])} |",
        f"| Rating | {rating}; {n['low_review_products']} of {n['products']} products have <10 reviews |",
        f"| Generic share of units | {n['generic_share']:.0%} |",
        "", "## Top products", "",
        "| # | Product | Price | Sold | ★ (reviews) | Seller |", "|---|---|--:|--:|---|---|",
    ]
    for i, p in enumerate(n["top"], 1):
        name = md_text(p.get("name"))[:70]
        lines.append(f"| {i} | [{name}]({link(p['url'])}) | {money(p['price'])} | {p['sold_count']:,} | "
                     f"{(p['rating'] or 0):.1f} ({p['review_count'] or 0}) | {md_text(p.get('seller_name'))} |")
    notes_file = f"notes/{n['category']}.md"
    lines += ["", "## Your notes", "", f"[{notes_file}]({notes_file})", ""]
    return "\n".join(lines)


def write_briefs(out, ns, run, has_v, top, n_products, detail=None):
    """Writes out/index.md + out/NN-<category>.md for the top niches (glob-deleting the old
    NN-*.md pages first). Creates out/notes/<category>.md with the manual checklist the first
    time a category gets a brief, and never touches it again -- that's where hand-filled
    sourcing notes live, and they must survive reruns."""
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "notes"), exist_ok=True)
    for old in glob.glob(os.path.join(out, "[0-9][0-9]-*.md")):
        os.remove(old)
    index = [f"# Market-entry shortlist — run `{run}`", "",
             f"{n_products:,} products with sales · {len(ns):,} niches · velocity: "
             f"{'yes' if has_v else 'not yet — needs a week of snapshots'}", "",
             "| # | Niche | Score | Units | Sellers | Top seller | Median price |",
             "|--:|---|--:|--:|--:|--:|--:|"]
    for i, n in enumerate(ns[:top], 1):
        fname = f"{i:02d}-{n['category']}.md"
        page = (detail or {}).get(n["category"], n)  # deeper stats for the brief, if crawled
        with open(os.path.join(out, fname), "w") as f:
            f.write(render(i, page, run, has_v))
        notes_path = os.path.join(out, "notes", f"{n['category']}.md")
        if not os.path.exists(notes_path):
            with open(notes_path, "w") as f:
                f.write(notes_template(n["category"]))
        index.append(f"| {i} | [{n['category']}]({fname}) | {n['score']:.3f} | {n['units']:,} | "
                     f"{n['sellers']} | {n['top1_share']:.0%} | {money(n['price_median'])} |")
    with open(os.path.join(out, "index.md"), "w") as f:
        f.write("\n".join(index) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--shortlist", type=int, default=50)
    ap.add_argument("--write-shortlist", action="store_true",
                    help="(re)write shortlist.txt; do this once after a full crawl, never from the weekly job")
    ap.add_argument("--out", default="briefs")
    a = ap.parse_args()

    con = db.connect_ro()
    run = latest_run(con)
    products = score_rows(load_rows(con))            # ranking: page 1 everywhere (fair)
    deep = {n["category"]: n for n in niches(score_rows(load_rows(con, max_page=None)))}
    max_page, missing = {}, {}
    for cat, mx, miss in con.execute(
            "SELECT category, MAX(page) FILTER (WHERE status = 'ok'), "
            "SUM(status IN ('stale', 'error', 'blocked')) FROM crawl_log WHERE run_id = ? GROUP BY category",
            (run,)):
        max_page[cat], missing[cat] = mx, miss or 0
    con.close()
    has_v = any(p.get("units_per_week") is not None for p in products)
    ns = niches(products)
    # Brief pages show every crawled page of their niche (deepened shortlist), keeping the
    # page-1 rank score so the index order stays comparable across niches.
    detail = {}
    for n in ns[:a.top]:
        k = max_page.get(n["category"]) or 1
        if k > 1 and n["category"] in deep:
            gaps = missing.get(n["category"], 0)
            depth = f"pages 1–{k}" + (f" ({gaps} page(s) missing: Daraz re-served an earlier page)" if gaps else "")
            detail[n["category"]] = {**deep[n["category"]], "score": n["score"], "depth": depth}

    write_briefs(a.out, ns, run, has_v, a.top, len(products), detail)
    if a.write_shortlist:
        with open(os.path.join(a.out, "shortlist.txt"), "w") as f:
            f.write("\n".join(n["category"] for n in ns[:a.shortlist]) + "\n")
    print(f"wrote {a.out}/index.md + {min(a.top, len(ns))} briefs"
          + (f" + shortlist of {min(a.shortlist, len(ns))}" if a.write_shortlist else ""))


if __name__ == "__main__":
    main()
