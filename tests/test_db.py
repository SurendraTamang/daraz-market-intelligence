import sqlite3

import pytest

from daraz import db


def add(con, nid, cat, run, sold, price=100.0):
    con.execute("INSERT INTO products (nid, name, price, category, sold_count, scraped_at) "
                "VALUES (?,?,?,?,?,?)", (nid, nid, price, cat, sold, run))


def log(con, run, cat, total, items=40, status="ok"):
    con.execute("INSERT INTO crawl_log (run_id, category, page, status, total_results, items) "
                "VALUES (?,?,1,?,?,?)", (run, cat, status, total, items))


def test_dedup_keeps_most_specific_category():
    con = db.connect(":memory:")
    log(con, "2026-10-12", "groceries", 4080)
    log(con, "2026-10-12", "tea", 300)
    add(con, "A", "groceries", "2026-10-12", 50)
    add(con, "A", "tea", "2026-10-12", 50)
    assert con.execute("SELECT nid, category FROM products_dedup").fetchall() == [("A", "tea")]


def test_dedup_without_crawl_log_keeps_one_row():  # legacy runs have no crawl_log
    con = db.connect(":memory:")
    add(con, "A", "groceries", "2026-08-19", 5)
    add(con, "A", "tea", "2026-08-19", 5)
    assert con.execute("SELECT category FROM products_dedup").fetchall() == [("groceries",)]


def test_velocity_latest_two_runs():
    con = db.connect(":memory:")
    log(con, "2026-10-05", "tea", 300)
    log(con, "2026-10-12", "tea", 300)
    add(con, "A", "tea", "2026-10-05", 2700)
    add(con, "A", "tea", "2026-10-12", 2800)   # "2.7K sold" -> "2.8K sold"
    add(con, "B", "tea", "2026-10-12", 10)     # new this week
    add(con, "C", "tea", "2026-10-05", 99)     # gone this week -> not in view
    rows = con.execute("SELECT nid, sold_before, days_between, units_per_week, is_new "
                       "FROM velocity ORDER BY nid").fetchall()
    assert rows == [("A", 2700, 7.0, 100.0, 0), ("B", None, None, None, 1)]


def test_velocity_ignores_runs_without_crawl_log():
    con = db.connect(":memory:")
    add(con, "A", "tea", "2026-08-19", 100)   # legacy run: no crawl_log rows
    log(con, "2026-10-12", "tea", 300)
    add(con, "A", "tea", "2026-10-12", 400)
    assert con.execute("SELECT is_new, units_per_week FROM velocity").fetchall() == [(1, None)]


def test_velocity_skips_fully_blocked_run():
    con = db.connect(":memory:")
    log(con, "2026-10-05", "tea", 300)
    log(con, "2026-10-12", "tea", 300)
    add(con, "A", "tea", "2026-10-05", 2700)
    add(con, "A", "tea", "2026-10-12", 2800)
    log(con, "2026-10-19", "tea", 300, items=0, status="blocked")  # fully blocked run, no products
    rows = con.execute("SELECT nid, sold_before, units_per_week FROM velocity").fetchall()
    assert rows == [("A", 2700, 100.0)]


def test_velocity_uses_latest_two_of_three_runs():
    con = db.connect(":memory:")
    log(con, "2026-09-28", "tea", 300)
    log(con, "2026-10-05", "tea", 300)
    log(con, "2026-10-12", "tea", 300)
    add(con, "A", "tea", "2026-09-28", 2000)
    add(con, "A", "tea", "2026-10-05", 2700)
    add(con, "A", "tea", "2026-10-12", 2800)
    rows = con.execute("SELECT nid, sold_before FROM velocity").fetchall()
    assert rows == [("A", 2700)]


def test_latest_run_prefers_most_complete_crawl():
    from analytics.analyze import latest_run
    con = db.connect(":memory:")
    assert latest_run(con) is None
    add(con, "A", "tea", "2026-08-19", 1)
    assert latest_run(con) == "2026-08-19"             # no crawl_log yet: newest snapshot
    for cat in ("tea", "mugs", "cups"):
        log(con, "2026-10-12", cat, 100)             # full run
    log(con, "2026-10-19", "tea", 100)               # newer partial weekly run
    assert latest_run(con) == "2026-10-12"


def test_connect_sets_wal_and_creates_index(tmp_path):
    p = str(tmp_path / "t.db")
    con = db.connect(p)
    assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    idx = con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_products_scraped_at'"
    ).fetchone()
    assert idx is not None
    con.close()


def test_connect_ro_can_select_but_not_write(tmp_path):
    p = str(tmp_path / "t.db")
    db.connect(p).close()
    ro = db.connect_ro(p)
    assert ro.execute("SELECT COUNT(*) FROM products_dedup").fetchone() == (0,)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO products (nid) VALUES ('x')")
    ro.close()


def test_connect_ro_raises_clear_error_on_fresh_legacy_db(tmp_path):
    p = str(tmp_path / "legacy.db")
    sqlite3.connect(p).execute("CREATE TABLE products (nid TEXT)")
    with pytest.raises(RuntimeError, match="db.connect"):
        db.connect_ro(p)


def test_connect_ro_opens_wal_db_after_writer_closed(tmp_path):
    p = str(tmp_path / "wal.db")
    db.connect(p).close()          # WAL mode; clean close removes -wal/-shm
    ro = db.connect_ro(p)          # must still open (mode=ro could not)
    assert ro.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


def test_velocity_compares_about_a_week_back_on_daily_runs():
    con = db.connect(":memory:")
    for day, sold in (("2026-10-05", 1000), ("2026-10-06", 1050), ("2026-10-11", 1300), ("2026-10-12", 1350)):
        log(con, day, "tea", 300)
        add(con, "A", "tea", day, sold)
    # latest 10-12 vs newest run at least 6 days older = 10-06 -> 300 units over 6 days
    assert con.execute("SELECT sold_before, days_between FROM velocity").fetchall() == [(1050, 6.0)]


def test_latest_run_prefers_newest_near_complete_run():
    from analytics.analyze import latest_run
    con = db.connect(":memory:")
    for cat in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"):
        log(con, "2026-10-12", cat, 100)
    for cat in ("a", "b", "c", "d", "e", "f", "g", "h", "i"):   # 9/10 = 90%: still counts as a full run
        log(con, "2026-10-13", cat, 100)
    assert latest_run(con) == "2026-10-13"
