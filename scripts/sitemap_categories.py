#!/usr/bin/env python3
"""Fetch ALL Daraz category slugs from the sitemap (fetched through the
configured transport, which also decompresses the .gz). Writes daraz/categories_all.py.

    python -m scripts.sitemap_categories
"""
import os
import re
import subprocess
import urllib.parse

TOKEN = next(l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("MRSCRAPER_TOKEN"))
INDEX = "https://www.daraz.com.np/sitemap-category-all.xml"


def fetch(url):
    enc = urllib.parse.quote(url, safe="")
    api = (f"https://api.mrscraper.com/?token={TOKEN}"
           f"&geoCode=np&proxyCountry=np&html=false&url={enc}")
    out = subprocess.run(["curl", "-s", "-m", "90", "-H", f"x-api-token: {TOKEN}", api],
                         capture_output=True, text=True).stdout
    import html
    m = re.search(r"<pre>(.*)</pre>", out, re.S)
    return html.unescape(m.group(1)) if m else out


def main():
    idx = fetch(INDEX)
    children = re.findall(r"<loc>(.*?)</loc>", idx)
    slugs = []
    for child in children:
        body = fetch(child)
        for loc in re.findall(r"<loc>(.*?)</loc>", body):
            slug = loc.rstrip("/").split("/")[-1]
            if slug and ".xml" not in slug:
                slugs.append(slug)
    slugs = sorted(set(slugs))
    os.makedirs("daraz", exist_ok=True)
    with open("daraz/categories_all.py", "w") as f:
        f.write("# Auto-generated from Daraz sitemap. Every catalog category slug.\n")
        f.write("CATEGORY_SLUGS = [\n")
        for s in slugs:
            f.write(f"    {s!r},\n")
        f.write("]\n")
    print(f"wrote daraz/categories_all.py: {len(slugs)} category slugs")


if __name__ == "__main__":
    main()
