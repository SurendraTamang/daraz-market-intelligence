"""SQLite schema + analysis views. One place for DDL. The writer (crawler) uses connect();
every reader (analyze/opportunity/brief/audit/app) uses connect_ro()."""
import os
import sqlite3

PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    nid TEXT, name TEXT, price REAL, original_price REAL, discount REAL,
    seller_id TEXT, seller_name TEXT, brand TEXT, category TEXT, location TEXT,
    rating REAL, review_count INTEGER, sold_count INTEGER, est_revenue REAL,
    image TEXT, scraped_at TEXT, raw_json TEXT,
    PRIMARY KEY (nid, category, scraped_at)
)"""

# One row per listing page fetched. Drives resume and the audit. scraped_at/run_id = RUN_ID.
CRAWL_LOG = """
CREATE TABLE IF NOT EXISTS crawl_log (
    run_id TEXT, category TEXT, page INTEGER, status TEXT,
    total_results INTEGER, items INTEGER, sold_items INTEGER, no_more_pages INTEGER, crawled_at TEXT,
    PRIMARY KEY (run_id, category, page)
)"""

# One row per (nid, run), kept under its most specific category = smallest page-1 totalResults.
# ponytail: window over the whole table on every read; materialize into a table if it gets slow.
PRODUCTS_DEDUP = """
CREATE VIEW products_dedup AS
SELECT * FROM (
    SELECT p.*, ROW_NUMBER() OVER (
        PARTITION BY p.nid, p.scraped_at
        ORDER BY COALESCE(c.total_results, 1000000000), p.category
    ) AS rn
    FROM products p
    LEFT JOIN crawl_log c ON c.run_id = p.scraped_at AND c.category = p.category AND c.page = 1
) WHERE rn = 1"""

# Latest crawled run vs the newest run at least 6 days older (else the oldest earlier one):
# Daraz rounds "2.7K sold", so day-over-day deltas are mostly rounding noise; a ~weekly window
# is what daily runs can trust. Only runs with crawl_log rows count, so the legacy
# (pre-crawl_log, a*-skewed) run never feeds velocity. Run ids start with YYYY-MM-DD.
# ponytail: days come from the RUN_ID date; pages fetched days into a long run get a slightly
# long interval (velocity under-estimated). Use crawl_log.crawled_at if that matters.
# `d` repeats products_dedup's ranking but pre-filtered to the 2 runs, for speed -- keep the two in sync.
VELOCITY = """
CREATE VIEW velocity AS
WITH runs AS (SELECT run_id AS r FROM crawl_log GROUP BY run_id HAVING SUM(items) > 0),
     cur AS (SELECT MAX(r) AS r FROM runs),
     prev AS (SELECT COALESCE(
         (SELECT MAX(r) FROM runs WHERE julianday(substr(r, 1, 10))
              <= julianday(substr((SELECT r FROM cur), 1, 10)) - 6),
         (SELECT MIN(r) FROM runs WHERE r < (SELECT r FROM cur))) AS r),
     d AS (SELECT * FROM (
        SELECT p.nid, p.category, p.sold_count, p.scraped_at, ROW_NUMBER() OVER (
            PARTITION BY p.nid, p.scraped_at
            ORDER BY COALESCE(c.total_results, 1000000000), p.category) AS rn
        FROM products p
        LEFT JOIN crawl_log c ON c.run_id = p.scraped_at AND c.category = p.category AND c.page = 1
        WHERE p.scraped_at IN ((SELECT r FROM cur), (SELECT r FROM prev))
     ) WHERE rn = 1)
SELECT n.nid, n.category, n.sold_count AS sold_now, o.sold_count AS sold_before,
       julianday(substr(n.scraped_at, 1, 10)) - julianday(substr(o.scraped_at, 1, 10)) AS days_between,
       -- a count that turns 0 is Daraz hiding it, not a fall: no velocity for that listing
       CASE WHEN n.sold_count = 0 AND o.sold_count > 0 THEN NULL ELSE
       (n.sold_count - o.sold_count) * 7.0
           / MAX(1, julianday(substr(n.scraped_at, 1, 10)) - julianday(substr(o.scraped_at, 1, 10)))
       END AS units_per_week,
       o.nid IS NULL AS is_new
FROM d n
LEFT JOIN d o ON o.nid = n.nid AND o.scraped_at = (SELECT r FROM prev)
WHERE n.scraped_at = (SELECT r FROM cur)"""


def path():
    return os.getenv("DARAZ_DB", "data.db")


def connect(p=None):
    """Writer connection: used by the crawler pipeline/spider. Sets up WAL (concurrent readers
    while the crawler writes) and the DDL/views, including a one-time index backfill."""
    con = sqlite3.connect(p or path())
    con.execute("PRAGMA journal_mode=WAL")
    for ddl in (PRODUCTS, CRAWL_LOG):
        con.execute(ddl)
    con.execute("CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at)")
    # Views are dropped and recreated every connect so definition changes land on existing DBs.
    for name, ddl in (("products_dedup", PRODUCTS_DEDUP), ("velocity", VELOCITY)):
        con.execute(f"DROP VIEW IF EXISTS {name}")
        con.execute(ddl)
    con.commit()
    return con


def connect_ro(p=None):
    """Read-only connection for every reader (analyze/opportunity/brief/audit/app). Never creates
    the DDL/views/index, so it can't lock or mutate the DB the crawler writes."""
    path_ = p or path()
    # Not `?mode=ro`: on a WAL DB with no writer open, the -shm file is gone and a mode=ro
    # handle can't recreate it ("unable to open database file"). query_only refuses writes.
    if not os.path.exists(path_):
        raise RuntimeError(f"{path_} does not exist")
    con = sqlite3.connect(path_)
    con.execute("PRAGMA query_only = ON")
    found = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='products_dedup'").fetchone()
    if not found:
        con.close()
        raise RuntimeError(
            "products_dedup view missing (fresh/legacy DB) -- run once: "
            'python -c "from daraz import db; db.connect().close()"')
    return con
