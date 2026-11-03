#!/usr/bin/env python3
"""Daily pipeline: crawl -> deepen -> audit (quality gate) -> outputs -> retain.

    python -m pipeline.run                         # today's run (RUN_ID = today's date)
    python -m pipeline.run --run 2026-10-14        # re-run / resume a day
    python -m pipeline.run --from outputs          # start at a later stage

Every stage is idempotent for its RUN_ID (crawl stages resume from crawl_log), so a failed day is
fixed by running the same command again. Writes logs/<run>/<stage>.log and runs/<run>.json, holds
.crawl.lock for the whole run, exits non-zero on failure and posts a macOS notification either way.
Run it through pipeline.sh (caffeinate + launchd).
"""
import argparse
import datetime
import json
import os
import random
import socket
import subprocess
import sys
import time

from daraz import db, transport
from daraz.crawl import parse_listing
from pipeline.audit import compare_page

STAGES = ("crawl", "deepen", "audit", "outputs")  # retain disabled until migration to PostgreSQL (Plan A)
FAST = ["-s", "DOWNLOAD_DELAY=0", "-s", "AUTOTHROTTLE_ENABLED=False", "-s", "DOWNLOAD_TIMEOUT=40"]
KEEP_RAW_DAYS = 7          # older runs keep only the fields analysis/velocity need
MAX_FAILED_SHARE = 0.05    # gate: page-1 fetches that stayed blocked/error after retries
MIN_COVERAGE = 0.90        # gate: live categories vs the best run so far
MIN_SPOT_MATCH = 0.90      # gate: stored price == live price on a re-fetch
LOCK = ".crawl.lock"
CRAWL_PASSES = 4           # resume passes until coverage is complete
DONE_COVERAGE = 0.98       # stop re-passing once live categories reach 98% of the best run


def gate(stats):
    """Quality gate for one run. Returns a list of failure reasons (empty = pass)."""
    fails = []
    if stats["page1_total"] and stats["page1_failed"] / stats["page1_total"] > MAX_FAILED_SHARE:
        fails.append(f"{stats['page1_failed']}/{stats['page1_total']} page-1 fetches failed")
    if stats["best_live"] and stats["live"] < MIN_COVERAGE * stats["best_live"]:
        fails.append(f"only {stats['live']} live categories vs {stats['best_live']} in the best run")
    if stats["spot_checked"] and stats["spot_price_ok"] / stats["spot_checked"] < MIN_SPOT_MATCH:
        fails.append(f"spot-check price match {stats['spot_price_ok']}/{stats['spot_checked']}")
    return fails


def wait_for_network(timeout=1800):
    """Block until Daraz and the proxy gateway resolve (a laptop's Wi-Fi drops; don't fail on it)."""
    t0 = time.time()
    while True:
        try:
            for host in ("www.daraz.com.np", os.environ.get("DECODO_HOST") or "b2b.liveproxies.io"):
                socket.getaddrinfo(host, 443)
            return
        except OSError:
            if time.time() - t0 > timeout:
                raise RuntimeError("no network for 30 min (DNS lookups failing)")
            time.sleep(30)


def crawl_complete(live, best, failed, total):
    """Crawl coverage is good enough to stop re-passing (Scrapy exits 0 even when it auto-stopped)."""
    return (not best or live >= DONE_COVERAGE * best) and (not total or failed / total < 0.02)


def coverage(run):
    con = db.connect_ro()
    one = lambda sql, *a: con.execute(sql, a).fetchone()[0] or 0  # noqa: E731
    out = (one("SELECT COUNT(DISTINCT category) FROM crawl_log WHERE run_id=? AND status IN ('ok','empty')", run),
           one("SELECT MAX(n) FROM (SELECT COUNT(DISTINCT category) n FROM crawl_log WHERE status IN ('ok','empty') "
               "AND run_id != ? GROUP BY run_id)", run),
           one("SELECT COUNT(*) FROM crawl_log WHERE run_id=? AND page=1 AND status IN ('blocked','error')", run),
           one("SELECT COUNT(*) FROM crawl_log WHERE run_id=? AND page=1", run))
    con.close()
    return out


def scrapy(run, log, env_extra, settings):
    env = {**os.environ, "RUN_ID": run, "PROXY": os.environ["PROXY"], "RAW_OFF": "1", **env_extra}
    cmd = [".venv/bin/scrapy", "crawl", "catalog", *FAST, *settings, "-s", f"LOG_FILE={log}"]
    subprocess.run(cmd, env=env, check=True)


def stage_crawl(run, logdir):
    # Resume passes until coverage is complete: each retries page-1s that ended blocked/error, and
    # a pass the spider auto-stopped (network loss, blocks) is simply continued by the next one.
    for i in range(1, CRAWL_PASSES + 1):
        wait_for_network()
        scrapy(run, f"{logdir}/crawl.log", {"DARAZ_ALL": "1", "MAX_PAGES": "1"},
               ["-s", "CONCURRENT_REQUESTS=8", "-s", "CONCURRENT_REQUESTS_PER_DOMAIN=8"])
        live, best, failed, total = coverage(run)
        if crawl_complete(live, best, failed, total):
            return {"passes": i, "live_categories": live}
    return {"passes": CRAWL_PASSES, "live_categories": live, "incomplete": True}  # the audit gate decides


def stage_deepen(run, logdir):
    if os.environ.get("DEEP_ALL"):  # every category, followed while its pages still show sales
        for i in (1, 2, 3):          # later passes resume + fill holes Daraz re-served as stale
            wait_for_network()
            scrapy(run, f"{logdir}/deepen_all.log", {"DARAZ_ALL": "1", "MAX_PAGES": "102"},
                   ["-s", "CONCURRENT_REQUESTS=8", "-s", "CONCURRENT_REQUESTS_PER_DOMAIN=8"])
        return {"mode": "all categories"}
    cats = []
    for path in ("briefs/shortlist.txt", "watchlist.txt"):  # top niches + niches under test
        if os.path.exists(path):
            cats += [s.strip() for s in open(path) if s.strip() and not s.lstrip().startswith("#")]
    if not cats:
        return {"skipped": "no shortlist or watchlist yet"}
    with open(f"{logdir}/deepen_categories.txt", "w") as f:
        f.write("\n".join(dict.fromkeys(cats)) + "\n")
    for i in (1, 2):  # second pass fills holes Daraz re-served as stale
        wait_for_network()
        scrapy(run, f"{logdir}/deepen.log",
               {"CATEGORIES_FILE": f"{logdir}/deepen_categories.txt", "MAX_PAGES": "102"},
               ["-s", "CONCURRENT_REQUESTS=4", "-s", "CONCURRENT_REQUESTS_PER_DOMAIN=4"])


def stage_audit(run, logdir):
    con = db.connect_ro()
    one = lambda sql, *a: con.execute(sql, a).fetchone()[0]  # noqa: E731
    stats = {
        "page1_total": one("SELECT COUNT(*) FROM crawl_log WHERE run_id=? AND page=1 "
                           "AND status NOT IN ('not_found','moved')", run),
        "page1_failed": one("SELECT COUNT(*) FROM crawl_log WHERE run_id=? AND page=1 "
                            "AND status IN ('blocked','error')", run),
        "live": one("SELECT COUNT(DISTINCT category) FROM crawl_log WHERE run_id=? AND status='ok'", run),
        "best_live": one("SELECT MAX(n) FROM (SELECT COUNT(DISTINCT category) n FROM crawl_log "
                         "WHERE status='ok' GROUP BY run_id)") or 0,
        "products": one("SELECT COUNT(*) FROM products WHERE scraped_at=?", run),
        "spot_checked": 0, "spot_price_ok": 0,
    }
    cats = [r[0] for r in con.execute(
        "SELECT category FROM crawl_log WHERE run_id=? AND page=1 AND status='ok'", (run,))]
    wait_for_network()
    for cat in random.sample(cats, min(5, len(cats))):
        try:
            data = parse_listing(transport.fetch(f"https://www.daraz.com.np/{cat}/?ajax=true&page=1"))
        except OSError:
            continue  # one failed spot fetch is not a data problem
        if data is None:
            continue
        stored = {n: (p, s) for n, p, s in con.execute(
            "SELECT nid, price, sold_count FROM products WHERE scraped_at=? AND category=?", (run, cat))}
        checked, price_ok, _ = compare_page(stored, data["mods"].get("listItems") or [])
        stats["spot_checked"] += checked
        stats["spot_price_ok"] += price_ok
    con.close()
    with open(f"{logdir}/audit.txt", "w") as f:  # the human-readable report, limitations first
        subprocess.run([sys.executable, "-m", "pipeline.audit", "--run", run], stdout=f, stderr=subprocess.STDOUT)
    fails = gate(stats)
    if fails:
        raise RuntimeError("quality gate failed: " + "; ".join(fails))
    return stats


def stage_outputs(run, logdir):
    weekly = datetime.date.fromisoformat(run).weekday() == 0  # Monday: refresh the shortlist
    with open(f"{logdir}/outputs.log", "w") as f:
        for cmd in (["analytics.brief", "--top", "20"] + (["--write-shortlist"] if weekly else []),
                    ["serve.export_json"], ["serve.export_dashboard"], ["analytics.ds_report"], ["analytics.watch"]):
            subprocess.run([sys.executable, "-m", *cmd], stdout=f, stderr=subprocess.STDOUT, check=True)
    return {"shortlist_refreshed": weekly}


def stage_retain(run, logdir):
    cutoff = (datetime.date.fromisoformat(run) - datetime.timedelta(days=KEEP_RAW_DAYS)).isoformat()
    con = db.connect()
    cur = con.execute(
        "UPDATE products SET raw_json = json_object('_page', json_extract(raw_json, '$._page'), "
        "'itemUrl', json_extract(raw_json, '$.itemUrl')) "
        "WHERE scraped_at < ? AND json_extract(raw_json, '$.name') IS NOT NULL", (cutoff,))
    slimmed = cur.rowcount
    con.commit()
    if datetime.date.fromisoformat(run).weekday() == 6:  # Sunday: give the space back
        con.execute("VACUUM")
    con.close()
    return {"rows_slimmed": slimmed, "cutoff": cutoff}


def notify(title, msg):
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                   check=False, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=datetime.date.today().isoformat())
    ap.add_argument("--from", dest="start", choices=STAGES, default="crawl")
    a = ap.parse_args()
    datetime.date.fromisoformat(a.run)  # RUN_ID must be a date
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # launchd starts us elsewhere
    os.environ.setdefault("PROXY", "decodo")

    logdir = f"logs/{a.run}"
    os.makedirs(logdir, exist_ok=True)
    os.makedirs("runs", exist_ok=True)
    if os.path.isdir(LOCK) and time.time() - os.path.getmtime(LOCK) > 12 * 3600:
        os.rmdir(LOCK)  # left by a crashed/killed run; no crawl runs 12h
    try:
        os.mkdir(LOCK)
    except FileExistsError:
        notify("Daraz pipeline", f"{a.run}: skipped — {LOCK} held by another crawl")
        print(f"{LOCK} exists — another crawl is running; skipping {a.run}")
        return 0
    summary = {"run": a.run, "started": datetime.datetime.now().isoformat(timespec="seconds"), "stages": {}}
    ok = True
    try:
        for name in STAGES[STAGES.index(a.start):]:
            t0 = time.time()
            try:
                out = globals()[f"stage_{name}"](a.run, logdir) or {}
                summary["stages"][name] = {"status": "ok", "seconds": round(time.time() - t0), **out}
            except Exception as e:
                summary["stages"][name] = {"status": "failed", "seconds": round(time.time() - t0),
                                           "error": str(e)[:500]}
                ok = False
                break
    finally:
        os.rmdir(LOCK)
        summary["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        summary["status"] = "ok" if ok else "failed"
        with open(f"runs/{a.run}.json", "w") as f:
            json.dump(summary, f, indent=2)
    failed = [n for n, s in summary["stages"].items() if s["status"] == "failed"]
    notify("Daraz pipeline", f"{a.run}: " + ("ok" if ok else f"FAILED at {failed[0]} — see logs/{a.run}"))
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
