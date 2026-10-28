# Daraz Nepal — Market Opportunity Report

*What to sell on Daraz.com.np, and where the openings are. Generated from a live crawl.*

## Scope & honesty notes (read first)

- **Dataset:** 14,098 products across 446 categories (5,550 with real sold-counts),
  683 sellers. Pulled from Daraz's category listing pages.
- **Alphabet skew:** the crawl was cut short mid-sweep, so coverage is heavy on
  A-* categories (acoustic, air, anti, aquarium, **automotive**). This is *not* a
  balanced marketplace sample — automotive is over-represented. But seller counts
  per category are real, so the low-competition signal holds.
- **"Demand Index" = price × all-time units sold.** A popularity proxy in Rs,
  **not monthly revenue, not audited GMV**, and cumulative (lifetime, not current
  velocity).
- **~16% of listings have no rating** (new products). **Generic share is
  overstated in electronics** — Daraz mislabels real brands as "No Brand."
- **Sold-counts are all-time.** To know what's selling *right now* needs a second
  crawl a week later, diffed. Not yet available.

---

## Headline finding: Automotive accessories is wide open

The single strongest signal in the data: **automotive parts/accessories have real
demand and almost no sellers.** A new entrant could dominate these categories.

| Category | Units sold | Sellers | Avg price |
|---|--:|--:|--:|
| automotive-code-readers / scan-tools | 21,102 | **3** | Rs 4,810 |
| automotive-doors | 16,536 | **1** | Rs 993 |
| automotive-dent-removal-tools | 16,990 | 5 | Rs 1,127 |
| automotive-alternators/generators | 10,841 | 5 | Rs 441 |
| automotive-oil-system-tools | 9,701 | 4 | Rs 714 |
| automotive-emergency-safety | 8,696 | 3 | Rs 1,558 |

**Concrete winners (cheap + huge volume):**
- Car Door Shock Absorber — Rs 361, **15,800 sold** (automotive-doors, 1 seller)
- Microfibre Wiping Cloth — Rs 97, 10,400 sold
- Plastic Rivets/Fasteners — Rs 324, 8,600 sold
- Blind-Spot Convex Mirrors — Rs 449, 8,100 sold
- Valve Caps / Tire accessories — Rs 302, 7,400 sold

**Why it's an opening:** demand in the thousands, 1–5 sellers, low unit cost
(Rs 100–700 for most accessories). Low competition = a real moat for a first mover.
*Caveat:* over-represented in this crawl — validate with a balanced re-crawl before
committing capital.

---

## The reliable play: cheap generic consumables & fashion basics

From the balanced categories (groceries, fashion, home, beauty):

- **97% of all units sold are generic ("No Brand").** You do **not** need a brand.
- **Volume concentrates under Rs 700.** Low capital, fast turnover.

**Proven low-capital winners:**
| Product | Price | Sold | Category |
|---|--:|--:|---|
| Waterproof bathroom slippers | Rs 149 | 6,100 | mens-fashion |
| Washing-machine tablet cleaner | Rs 119 | 4,100 | groceries |
| Scalp massager brush | Rs 72 | 4,100 | hair-care |
| Gym muscle hoodies | Rs 399 | 4,600 | mens-fashion |
| Cotton boxers (4-pack) | Rs 549 | 3,000 | mens-fashion |

---

## Quality-gap arbitrage (sell it, do it better)

Products selling thousands **despite weak ratings (<4.4★)** — demand exists, the
incumbents are mediocre. Source a better version, win on reviews:

- Cotton boxers (4-pack) — 3,000 sold, 4.1★
- Auto water-jar pump — 3,700 sold, 4.1★
- Heatless hair curlers — 2,900 sold, 4.1★

---

## What to avoid

- **Electronics** (laptops, tablets, phones): Rs 8k–60k capital, entrenched
  official stores (YalaMart, Blackview), real brands. Hard entry.

---

## Recommendation

1. **Best moat opportunity:** automotive accessories — thousands of units, 1–5
   sellers, cheap parts. Higher-effort sourcing but almost no competition.
   *Validate first with a balanced re-crawl.*
2. **Safest low-capital start:** generic consumables + fashion basics under Rs 700.
   Proven volume, no brand needed, fast turnover.
3. **The edge either way:** target quality gaps — high-sold, low-rated products you
   can beat on quality.

## Next step that actually matters

Everything above is **all-time popularity**. To prove these picks are *rising* (not
fading), run a **weekly crawl** on a curated set of categories and diff the
sold-counts. In 3–4 weeks that turns "these are popular" into "these are trending" —
the difference between a guess and a validated bet.
