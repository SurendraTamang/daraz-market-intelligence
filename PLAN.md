# Plan — from data to a running e-commerce business

## Where we are
- Tool built: Scrapy + MrScraper + sitemap → SQLite → analysis (Opportunity Score).
- Data so far: 14k products, but A-alphabet-skewed. **Full balanced scrape running now.**
- Strongest signal: **automotive accessories** — thousands of units, 1–5 sellers,
  cheap parts. Plus the safe fallback: **generic consumables / fashion <Rs 700**.

## The plan (4 phases, run in parallel where possible)

### Phase 1 — Finish the data (this week, automated)
- Full page-1 scrape of all 5,932 categories is running (chunked, auto-resume).
- **Goal:** a *balanced* dataset so we know if automotive is a real opportunity or
  just an artifact of the A-skew. Re-run `REPORT.md` on the complete data.
- **Decision gate:** does automotive (and any new niche) still show <5 sellers +
  high demand across the full crawl? If yes → it's real.

### Phase 2 — Validate demand is *rising*, not fading (weeks 1–4)
- Set up a **weekly crawl** on a curated ~30-category set (the real opportunities).
- Diff `sold_count` week-over-week → rank what's **trending up**.
- **Why:** current numbers are all-time. A product with 10k lifetime sales that
  sold 0 this month is a trap. Velocity separates live demand from dead stock.

### Phase 3 — Validate *supply* (you, manually — the part data can't do)
For the top 3–5 candidate products:
- Can you **source** it? (AliExpress/local wholesaler, MOQ, unit cost)
- **Margin:** landed cost vs Daraz selling price. Need ~2–3× to survive fees + ads.
- **Incumbent check:** open the top seller's listing — reviews, photos, price.
  Where's the quality gap you'd beat?
- Automotive needs real sourcing legwork; consumables are easy to source.

### Phase 4 — Start small, then scale
- Launch **1–2 SKUs** on Daraz as a seller. Low capital (Rs 20–40k stock).
- Track: units/week, rating, return rate. Kill losers fast, reorder winners.
- Scale the winners; add adjacent SKUs in the same category.

## The call on what to sell first
Run **two tracks**:
1. **Safe track (start now):** a generic consumable/fashion SKU under Rs 700
   (washing tablets, slippers, scalp brush). Low risk — its real purpose is to
   **learn the Daraz seller mechanics** (listing, fulfillment, ads, returns).
2. **Upside track (validate first):** automotive accessories — the low-competition
   moat. Confirm with the full scrape + a sourcing check before committing capital.

Learn the game cheap on track 1 while de-risking the big bet on track 2.

## Productize later (optional)
If the tool's picks prove out (Phase 2–3), the *same intelligence* becomes a
product for other Nepali sellers: "market-entry reports" per category. But **prove
it on your own store first** — a tool that made *you* money sells itself.

## Immediate next steps
1. Let the full scrape finish (auto-resuming). — in progress
2. I set up the weekly velocity crawl (scheduled). — on your go
3. You pick one safe-track SKU and check sourcing this week.
