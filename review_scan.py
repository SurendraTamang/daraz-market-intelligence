#!/usr/bin/env python3
"""Mine Daraz reviews of high-demand, weakly rated products: is the gap fixable?

    PROXY=liveproxies python review_scan.py --top 30          # -> reviews/*.json + reviews/scan.csv

Candidates: page-1 products of the latest run with >= 300 sold, Rs 150-1,500, no brand, rated < 4.2
over >= 20 reviews, in a niche with HHI < 2,500; skin/medical/cosmetic items excluded (refund and
harm risk); at most 2 per niche. Each one's 1-3 star review text is tagged by complaint theme:
fixable (build, fit, battery, leak, wrong/damaged item) vs inherent (pain/harm). No buyer names kept.
"""
import argparse
import json
import os
import re
import time

import pandas as pd

from analyze import load_rows, score_rows
from daraz import db, transport
from ds_report import niche_table

EXCLUDE = re.compile(r"hair remov|wax|cream|ointment|serum|lotion|lipstick|kajal|eyeliner|perfume|fragrance|"
                     r"cologne|dental|teeth|wart|skin|herbal|oil\b|capsule|tablet|supplement|condom|sex|"
                     r"medicine|sleep|massag|brace|posture|vr |vr-|earphone|headphone|baby", re.I)
THEMES = {
    "harm": r"pain|burn|rash|wound|ghau|blood|allerg|pol(cha|xa)|itch|chilaun",
    "breaks / build": r"broke|break|tut|fut|crack|fragile|cheap|plastic|poor quality|low quality|patalo|thin|weak",
    "fit / size": r"\bfit|size|small|big|sano|thulo|mildaina|mile?na|length|short|long",
    "battery / charge": r"batter|charg|cell\b",
    "leak": r"leak|chuh",
    "wrong / damaged / used": r"wrong|different|damag|used|purano|missing|duplicate|old one|defect|scratch",
    "doesn't work": r"not work|doesn.?t work|didn.?t work|kam (gard|chain|xain|garena)|kaam (gard|chain|xain)|useless|waste",
}
FIXABLE = ("breaks / build", "fit / size", "battery / charge", "leak", "wrong / damaged / used")


def candidates(top, skip):
    con = db.connect_ro()
    rows = score_rows(load_rows(con))
    con.close()
    p = pd.DataFrame([{k: r[k] for k in ("nid", "name", "category", "price", "sold_count", "rating",
                                          "review_count", "seller_id", "score", "generic", "url")} for r in rows])
    p["seller"] = p.seller_id.fillna("nid:" + p.nid.astype(str))
    p["review_count"] = p.review_count.fillna(0)
    nt = niche_table(p)
    p = p.join(nt[["hhi"]], on="category")
    c = p[(p.sold_count >= 300) & p.price.between(150, 1500) & p.generic & (p.hhi < 2500)
          & (p.review_count >= 20) & (p.rating < 4.2) & ~p.nid.isin(skip)]
    c = c[~c.name.str.contains(EXCLUDE) & ~c.category.str.contains(EXCLUDE)]
    c = c.sort_values("score", ascending=False).groupby("category").head(2)
    return c.head(top)


def fetch_reviews(nid, max_pages):
    out, page, pages, scores = [], 1, 1, None
    while page <= min(pages, max_pages):
        for attempt in range(3):
            try:
                m = json.loads(transport.fetch(
                    f"https://my.daraz.com.np/pdp/review/getReviewList?itemId={nid}&pageSize=50&filter=0"
                    f"&sort=0&pageNo={page}"))["model"]
                break
            except Exception:
                time.sleep(3)
        else:
            break
        pages, scores = m["paging"]["totalPages"], scores or m["ratings"]["scores"]
        out += [{"rating": r["rating"], "text": r.get("reviewContent") or "", "date": r.get("reviewTime"),
                 "sku": r.get("skuInfo"), "likes": r.get("likeCount", 0)} for r in m["items"]]
        page += 1
        time.sleep(1.2)
    return out, scores


def tag(reviews):
    low = [r for r in reviews if r["rating"] <= 3 and r["text"].strip()]
    counts = {k: sum(bool(re.search(rx, r["text"], re.I)) for r in low) for k, rx in THEMES.items()}
    return low, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--pages", type=int, default=4)
    a = ap.parse_args()
    os.makedirs("reviews", exist_ok=True)
    done = {json.load(open(f"reviews/{f}")).get("nid") for f in os.listdir("reviews") if f.endswith(".json")}
    rows = []
    for r in candidates(a.top, done).to_dict("records"):
        reviews, scores = fetch_reviews(r["nid"], a.pages)
        low, counts = tag(reviews)
        json.dump({"nid": r["nid"], "name": r["name"], "category": r["category"], "scores_5_to_1": scores,
                   "reviews": reviews}, open(f"reviews/{r['nid']}.json", "w"), ensure_ascii=False, indent=1)
        n = max(len(low), 1)
        rows.append({**{k: r[k] for k in ("nid", "name", "category", "price", "sold_count", "rating", "hhi", "score")},
                     "low_reviews": len(low), "fixable_share": round(sum(counts[k] for k in FIXABLE) / n, 2),
                     "harm_share": round(counts["harm"] / n, 2), **counts, "url": r["url"]})
        print(f"{r['sold_count']:>6} sold {r['rating']:.2f}★ | {len(low):3} low | fixable {rows[-1]['fixable_share']:.0%} "
              f"harm {rows[-1]['harm_share']:.0%} | {r['name'][:60]}")
    pd.DataFrame(rows).to_csv("reviews/scan.csv", index=False)


if __name__ == "__main__":
    main()
