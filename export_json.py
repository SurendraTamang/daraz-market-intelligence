#!/usr/bin/env python3
"""Export data.db -> frontend/src/data.json (bundled by the React build).

Run after each crawl:  python export_json.py
"""
import json
import os

from analyze import build_payload

OUT = "frontend/src/data.json"  # imported (bundled) so the single-file build works


def main():
    data = build_payload()  # honours DARAZ_DB
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"wrote {OUT}: {data['meta']['products']} products, "
          f"{data['meta']['categories']} categories, {os.path.getsize(OUT)//1024}KB")


if __name__ == "__main__":
    main()
