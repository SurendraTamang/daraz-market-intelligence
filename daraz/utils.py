import html
import json
import re


def parse_sold_count(text):
    """'2.7K sold'->2700, '10K+ sold'->10000, '2M sold'->2000000, '500 sold'->500, ''/None->0."""
    if not text:
        return 0
    m = re.search(r"([\d.]+)\s*([KkMm]?)", text)
    if not m:
        return 0
    mult = {"K": 1_000, "M": 1_000_000}.get(m.group(2).upper(), 1)
    return int(float(m.group(1)) * mult)


def extract_json(text):
    """MrScraper wraps the ajax JSON in <pre>...</pre> and HTML-escapes it. Unwrap + parse."""
    m = re.search(r"<pre>(.*)</pre>", text, re.S)
    body = html.unescape(m.group(1)) if m else text
    return json.loads(body)


def to_float(v):
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    return float(m.group(0)) if m else None


def to_int(v):
    f = to_float(v)
    return int(f) if f is not None else None
