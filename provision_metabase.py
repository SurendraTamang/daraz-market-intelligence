#!/usr/bin/env python3
"""Auto-build the Daraz market dashboard in Metabase via its REST API.

Run AFTER `docker compose up -d metabase` (wait for it to boot). Idempotent-ish:
creates the admin user on first run; on later runs pass the same creds via env.

    python provision_metabase.py

Env (optional): MB_URL, MB_EMAIL, MB_PASSWORD, MB_DB_PATH.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

MB = os.getenv("MB_URL", "http://localhost:3000")
EMAIL = os.getenv("MB_EMAIL", "admin@daraz.local")
PASSWORD = os.getenv("MB_PASSWORD", "Daraz-admin1")
DB_PATH = os.getenv("MB_DB_PATH", "/data/data.db")


def api(method, path, session=None, body=None):
    data = json.dumps(body).encode() if body is not None else (
        b"{}" if method in ("POST", "PUT") else None
    )
    req = urllib.request.Request(f"{MB}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}") from None


def wait_up():
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{MB}/api/health", timeout=5)
            return
        except Exception:
            time.sleep(3)
    sys.exit("Metabase never came up at " + MB)


def get_session():
    """Log in if already set up; otherwise run first-time setup to create the admin."""
    setup_token = api("GET", "/api/session/properties").get("setup-token")
    if setup_token:
        res = api("POST", "/api/setup", body={
            "token": setup_token,
            "prefs": {"site_name": "Daraz Market Analyzer", "allow_tracking": False},
            "user": {
                "first_name": "Daraz", "last_name": "Admin",
                "email": EMAIL, "password": PASSWORD, "site_name": "Daraz",
            },
        })
        return res["id"]
    return api("POST", "/api/session", body={"username": EMAIL, "password": PASSWORD})["id"]


def get_or_create_db(session):
    for db in api("GET", "/api/database", session=session).get("data", []):
        if db.get("name") == "Daraz":
            return db["id"]
    db = api("POST", "/api/database", session=session,
             body={"engine": "sqlite", "name": "Daraz", "details": {"db": DB_PATH}})
    return db["id"]


def native_card(name, sql, display="table", viz=None):
    return {
        "name": name,
        "display": display,
        "visualization_settings": viz or {},
        "dataset_query": {"type": "native", "native": {"query": sql}},
    }


CARDS = [
    native_card(
        "Top products by est. revenue",
        "SELECT name, category, price, sold_count, est_revenue, rating, seller_name "
        "FROM products ORDER BY est_revenue DESC LIMIT 50"),
    native_card(
        "Best categories by revenue",
        "SELECT category, SUM(est_revenue) AS total_revenue, SUM(sold_count) AS units_sold, "
        "ROUND(AVG(price)) AS avg_price FROM products GROUP BY category ORDER BY total_revenue DESC",
        "bar", {"graph.dimensions": ["category"], "graph.metrics": ["total_revenue"]}),
    native_card(
        "Seller concentration (low = opportunity)",
        "SELECT category, COUNT(DISTINCT seller_id) AS distinct_sellers, COUNT(*) AS listings "
        "FROM products GROUP BY category ORDER BY distinct_sellers ASC",
        "bar", {"graph.dimensions": ["category"], "graph.metrics": ["distinct_sellers"]}),
    native_card(
        "Price vs demand",
        "SELECT price, sold_count, category FROM products WHERE price > 0 AND sold_count > 0",
        "scatter", {"graph.dimensions": ["price"], "graph.metrics": ["sold_count"]}),
    native_card(
        "Demand gaps: high sold, low rating",
        "SELECT name, category, sold_count, rating, review_count, price FROM products "
        "WHERE rating > 0 AND rating < 4.3 AND sold_count >= 1000 ORDER BY sold_count DESC LIMIT 30"),
    native_card(
        "Top sellers by revenue",
        "SELECT seller_name, COUNT(*) AS products, SUM(est_revenue) AS revenue, "
        "SUM(sold_count) AS units_sold FROM products GROUP BY seller_name ORDER BY revenue DESC LIMIT 25"),
]


def main():
    print("Waiting for Metabase...")
    wait_up()
    session = get_session()
    print("Logged in.")
    db_id = get_or_create_db(session)
    print(f"Database id={db_id}. Syncing schema...")
    try:
        api("POST", f"/api/database/{db_id}/sync_schema", session=session)
    except Exception:
        pass
    time.sleep(5)

    dash_id = api("POST", "/api/dashboard", session=session,
                  body={"name": "Daraz Market Opportunity"})["id"]

    dashcards = []
    for i, spec in enumerate(CARDS):
        spec["dataset_query"]["database"] = db_id
        card = api("POST", "/api/card", session=session, body=spec)
        print(f"  card: {spec['name']} (id={card['id']})")
        dashcards.append({
            "id": -(i + 1), "card_id": card["id"],
            "row": (i // 2) * 6, "col": (i % 2) * 12, "size_x": 12, "size_y": 6,
        })

    api("PUT", f"/api/dashboard/{dash_id}", session=session, body={"dashcards": dashcards})
    print(f"\nDone. Dashboard: {MB}/dashboard/{dash_id}")
    print(f"Login: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
