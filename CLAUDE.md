# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Daraz.com.np market analyzer: Scrapy crawls category listing JSON → SQLite (`data.db`) → an "Opportunity Score" that ranks what a new seller should stock. Several read-only frontends sit on the same DB. `PLAN.md` holds the business plan (balanced full scrape → weekly velocity diff → manual sourcing check). `REPORT.md` holds findings and their data caveats.

## Daily pipeline (scheduled)

Project lives at `~/Projects/product-market-analyzer` (Desktop path is a symlink; launchd can't list Desktop folders).
launchd job `com.daraz.pipeline` (`~/Library/LaunchAgents/com.daraz.pipeline.plist`, copy of the repo file) runs `pipeline.sh` daily 06:00 → `pipeline.py`:
crawl (page 1, all categories, 2 passes) → deepen (`briefs/shortlist.txt`, 2 passes incl. holes) → audit (quality gate: ≤5% failed page-1, ≥90% of best live-category count, ≥90% spot-check price match) → outputs (briefs, `export_json.py`, `export_dashboard.py`; shortlist refreshed Mondays) → retain (raw_json slimmed after 7 days; VACUUM Sundays).
`DEEP_ALL=1 ./pipeline.sh --run <date> --from deepen` crawls every category deep (~20k pages, 5–7 h).
Per run: `logs/<date>/`, `runs/<date>.json`, macOS notification. Fix a failed day: `./pipeline.sh --run <date> [--from <stage>]`.
`launchctl kickstart gui/$(id -u)/com.daraz.pipeline` runs it now; `launchctl bootout gui/$(id -u)/com.daraz.pipeline` disables it.
The claude.ai dashboard (`dashboard/*.json` → Artifact) only refreshes when Claude re-uploads the files.

## Commands

Run all commands from the **repo root**. Every path (`data.db`, `raw/`, `.env`, `frontend/src/data.json`) is relative to it.

```bash
source .venv/bin/activate              # pip install -r requirements.txt; .env needs LIVEPROXIES_HOST/PORT/USER/SESSIONS (PROXY=liveproxies) or MRSCRAPER_TOKEN (PROXY=mrscraper)
pytest tests/                          # daraz/crawl, transport, db, analyze, brief, audit, utils parsers
pytest tests/test_parse.py::test_parse_sold_count

# Every crawl needs PROXY (none|liveproxies|mrscraper) and RUN_ID (start date = snapshot id; reuse it to resume)
date +%F > .run_id                                                               # ONLY when starting a new snapshot
FAST='-s CONCURRENT_REQUESTS=16 -s CONCURRENT_REQUESTS_PER_DOMAIN=16 -s DOWNLOAD_DELAY=0 -s AUTOTHROTTLE_ENABLED=False -s DOWNLOAD_TIMEOUT=40'  # proxy only; ~170 pages/min
caffeinate -is env PROXY=liveproxies RUN_ID=$(cat .run_id) DARAZ_ALL=1 RAW_OFF=1 scrapy crawl catalog $FAST -s LOG_FILE=crawl.log  # all 5,932 categories, MAX_PAGES=3; rerun = resume
caffeinate -is env PROXY=liveproxies RUN_ID=$(cat .run_id) DARAZ_ALL=1 RAW_OFF=1 MAX_PAGES=102 scrapy crawl catalog $FAST  # deepen, same snapshot
kill -INT <python scrapy pid>   # graceful stop (not the caffeinate/zsh wrapper pid); resume later with the same RUN_ID
DARAZ_DB=scratch.db ...                                                           # any script/crawl against another DB — ALWAYS for test crawls: a small test run in data.db becomes the velocity baseline
python audit.py [--spot 5]   # content audit of the latest run — before trusting results
python brief.py [--write-shortlist]   # briefs/index.md + NN-<niche>.md; shortlist.txt only with the flag
python sitemap_categories.py # regenerates daraz/categories_all.py

python export_json.py                  # data.db -> frontend/src/data.json (bundled snapshot)
uvicorn api:app --port 8000            # live /api/data for the React app
streamlit run app.py                   # internal slider tool, :8501
python opportunity.py --top 20          # CLI ranking (DARAZ_DB=... for another DB)
python report.py [--db ...]            # writes report.html
sqlite3 data.db < analysis.sql         # same SQL as the Metabase panels

cd frontend && npm run dev | build | build:single | deploy   # deploy = Cloudflare Pages project "daraz-market"
VITE_API_URL=http://localhost:8000 npm run dev               # live mode, falls back to bundled data.json
```

Metabase: `sqlite3 data.db ".backup warehouse/dashboard.db"` → `sqlite3 warehouse/dashboard.db "PRAGMA journal_mode=DELETE"` (data.db is WAL; Metabase mounts `warehouse/` read-only and can't open a WAL file) → `docker compose up -d metabase` → `python provision_metabase.py`. Metabase must read the **snapshot**, never live `data.db`, because a mid-write SQLite file reads as "malformed".

## Architecture

**Crawl path:** `daraz/spiders/catalog.py` requests `https://www.daraz.com.np/<slug>/?ajax=true&page=N` → `TransportMiddleware` (`daraz/middlewares.py`) dispatches on `PROXY` (`none | liveproxies | mrscraper`; see `daraz/transport.py`) → the response is JSON (direct/liveproxies) or wrapped in HTML-escaped `<pre>` (mrscraper), which `utils.extract_json` unwraps → items come from `mods.listItems` → the pipeline writes to the `products` and `crawl_log` tables.

- **Category source:** `daraz/config.py`. `CATEGORY_SLUGS` holds 14 curated slugs. `DARAZ_ALL=1` swaps in `daraz/categories_all.py` (auto-generated, don't hand-edit). Top-level nav slugs are JS landing pages with no `listItems`. A new slug must be probed for `listItems` first.
- **Env knobs:** `PROXY` (required), `RUN_ID` (required), `MAX_PAGES` (default 3; the spider also stops at the first page with no sold items or `noMorePages`), `DARAZ_ALL`, `CATEGORIES_FILE`, `RAW_OFF`, `DARAZ_DB`.
- **Schema (`daraz/db.py`):** `products` PK `(nid, category, scraped_at)`, `scraped_at = RUN_ID`. `crawl_log` has one row per page fetched. Views: `products_dedup` (one row per product per run, most specific category) and `velocity` (latest vs previous run).
- **Single writer:** the pipeline commits per item (crash-safe) and retries on locked/readonly errors. Never run two crawls against `data.db` at once.
- **Cost:** low concurrency in `settings.py` on purpose, because every request spends paid proxy quota (liveproxies GB or MrScraper credits, depending on `PROXY`). `ROBOTSTXT_OBEY = False` (Daraz disallows `/catalog/`; this is for personal research only).

**Analysis path:** `analyze.py` (`build_payload`, `score_rows`) is the only scorer; `export_json.py` (static), `api.py` (live), `opportunity.py`, `app.py` and `brief.py` all call it and must emit the same shape (`frontend/src/types.ts`). Score = weighted mean of D .30, V .20, C .20, Q .10, A .10, G .10, then `* (0.4 + 0.6D)` (demand gate). D = demand (percentile of lifetime sold), A = affordability (1 − percentile of price), Q = rating gap (neutral 0.5 under 10 reviews), C = 1 − top-1 seller share of units in the leaf category, V = velocity (weight 0 until 2 runs exist), G = generic brand share.

## Gotchas

- **Daraz's "X sold" is a rolling recent window, not lifetime** (verified 2026-10-14: 5.2k of 145k matched listings fell in 2 days; out-of-season summer items fell steadily). A count turning 0 means hidden, not a fall. Week-over-week change = acceleration. `analyze.MIN_VELOCITY_DAYS = 6`: shorter comparisons are rounding noise and are not scored.
- `watch.py` niche deltas are like-for-like (page-1 counts, units only on listings in both runs) because runs crawl niches to different depths.

- **Daraz pagination needs the page-1 session cookie.** Without it `?page=N>1` silently re-serves page 1. The spider uses one cookie jar + one sticky proxy IP per category (`meta["cookiejar"]=slug`, session = crc32(slug)), and on resume re-fetches page 1 before jumping to page N. Never set `COOKIES_ENABLED=False`.
- Dead sitemap slugs return Daraz's HTML error page (`wh_pid=/lazada/channel/np/common/error`) with HTTP 200 → logged `not_found` (no retries).

- Readers use `db.connect_ro()` (normal connection + `PRAGMA query_only`), safe during a crawl; only the crawler uses `db.connect()`. Don't use `?mode=ro` on the WAL DB — it fails when no writer is open.
- `caffeinate -is` is required for long crawls: a sleeping Mac pauses the crawl (Scrapy's elapsed time excludes sleep).

- `analyze.py` is the only scorer (app, CLI, API, export, briefs import it). `report.py`, `analysis.sql` and Metabase panels still read raw `products` across **all runs**, so they double-count once there are multiple snapshots. Use `products_dedup` filtered to one `scraped_at`.
- Resume is per `RUN_ID` via `crawl_log`. Reusing a RUN_ID continues it; a new RUN_ID is a new snapshot. Use the pinned `.run_id` for resume/deepen, never `$(date +%F)` (a different day = a new snapshot = full re-crawl).
- Scoring uses the run covering the most categories (`analyze.latest_run`). Weekly partial runs only feed `velocity`, which ignores runs without `crawl_log` rows (the legacy August data).
- `crawl_log.status` is one of `ok | empty | blocked | error | stale | not_found | moved`. `stale` = Daraz served the previous page's items again for page N (it happens; detected by nid overlap and retried on a new IP). `not_found` (404/410, dead sitemap slug) and `moved` (non-captcha redirect, renamed category) are terminal but don't count toward the auto-stop. The spider stops itself when >20% of the last 100 pages END `blocked`/`error` after all retries (min 50 samples; captchas at 16 concurrency are ~7% of attempts and clear on retry, at 32 they hit ~20%); a product write failure stops the crawl immediately with reason `db_error`.
- liveproxies PROXY PASSWORD lives in Keychain (`liveproxies-proxy`); host/port/user in `.env`. The B2B dashboard API token (plan/usage lookups only, not used for crawling) is a separate Keychain entry, `liveproxies-api-token`.
- liveproxies has no Nepal exits — Daraz.com.np serves identical listing JSON to India/US exits. `LIVEPROXIES_USER` (account id + access code, e.g. `LVxxxxxxxx-lv_in`, no session suffix) needs a random sticky-session suffix (`-1`..`-${LIVEPROXIES_SESSIONS}`) appended per request to get IP rotation; a bare username with no suffix fails with CONNECT 504/500.
- As of 2026-10-12: the current liveproxies plan (100 GB) expires 2026-10-18.
- Velocity compares the latest two runs; Daraz rounds counts ("2.7K sold"), so it's coarse above ~1K lifetime sold.
- Rebrand the frontend in `frontend/src/brand.ts` and through the accent color in `frontend/tailwind.config.js`.
