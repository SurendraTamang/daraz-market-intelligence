#!/usr/bin/env python3
"""Generate a self-contained HTML market-opportunity report from data.db.

    python report.py            # writes report.html
    python report.py --db warehouse/dashboard.db

No framework, no server, no CDN — one styled static page. Regenerate after a crawl.
"""
import argparse
import html
import sqlite3

ACCENT = "#F2A93B"


def q(con, sql):
    con.row_factory = sqlite3.Row
    return con.execute(sql).fetchall()


def money(n):
    n = float(n or 0)
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def num(n):
    return f"{int(n or 0):,}"


def esc(s):
    return html.escape(str(s if s is not None else ""))


def verdict(avg_price, sellers):
    """Cheap to stock + fragmented sellers = easiest entry."""
    if avg_price <= 1200 and sellers >= 40:
        return ("start", "Start here")
    if avg_price >= 8000:
        return ("hard", "Hard entry")
    return ("consider", "Consider")


def bar(value, vmax, cls):
    pct = 0 if not vmax else max(2, round(100 * value / vmax))
    return f'<div class="bar"><span class="{cls}" style="width:{pct}%"></span></div>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data.db")
    ap.add_argument("--out", default="report.html")
    args = ap.parse_args()
    con = sqlite3.connect(args.db)

    total_products = q(con, "SELECT COUNT(*) c FROM products")[0]["c"]
    total_units = q(con, "SELECT SUM(sold_count) s FROM products")[0]["s"] or 0
    total_rev = q(con, "SELECT SUM(est_revenue) s FROM products")[0]["s"] or 0
    total_sellers = q(con, "SELECT COUNT(DISTINCT seller_id) c FROM products")[0]["c"]
    ncats = q(con, "SELECT COUNT(DISTINCT category) c FROM products")[0]["c"]

    cats = q(con, """
        SELECT category,
               SUM(est_revenue) rev, SUM(sold_count) units, ROUND(AVG(price)) avg_price,
               COUNT(*) listings, COUNT(DISTINCT seller_id) sellers
        FROM products GROUP BY category ORDER BY rev DESC
    """)
    rev_max = max((c["rev"] for c in cats), default=1)
    sell_max = max((c["sellers"] for c in cats), default=1)

    top = q(con, """
        SELECT name, category, price, sold_count, est_revenue, rating, seller_name
        FROM products ORDER BY est_revenue DESC LIMIT 15
    """)
    gaps = q(con, """
        SELECT name, category, sold_count, rating, price
        FROM products WHERE rating>0 AND rating<4.4 AND sold_count>=1000
        ORDER BY sold_count DESC LIMIT 12
    """)
    cheap = q(con, """
        SELECT name, category, price, sold_count, rating
        FROM products WHERE price<=1000 AND price>0 ORDER BY sold_count DESC LIMIT 12
    """)

    # ---- build category matrix rows
    cat_rows = ""
    for c in cats:
        vclass, vlabel = verdict(c["avg_price"], c["sellers"])
        cat_rows += f"""<tr>
          <td class="name">{esc(c['category'])}</td>
          <td class="figs">Rs {money(c['rev'])}{bar(c['rev'], rev_max, 'rev')}</td>
          <td class="r">{num(c['units'])}</td>
          <td class="r">Rs {num(c['avg_price'])}</td>
          <td class="figs">{c['sellers']}{bar(c['sellers'], sell_max, 'sell')}</td>
          <td><span class="pill {vclass}">{vlabel}</span></td>
        </tr>"""

    def product_rows(rows, cols):
        out = ""
        for r in rows:
            tds = "".join(cols_fn(r) for cols_fn in cols)
            out += f"<tr>{tds}</tr>"
        return out

    top_rows = product_rows(top, [
        lambda r: f'<td class="name">{esc(r["name"])[:60]}</td>',
        lambda r: f'<td class="tag">{esc(r["category"])}</td>',
        lambda r: f'<td class="r">Rs {num(r["price"])}</td>',
        lambda r: f'<td class="r">{num(r["sold_count"])}</td>',
        lambda r: f'<td class="r strong">Rs {money(r["est_revenue"])}</td>',
        lambda r: f'<td class="r">{(r["rating"] or 0):.1f}★</td>',
        lambda r: f'<td class="muted">{esc(r["seller_name"])}</td>',
    ])
    gap_rows = product_rows(gaps, [
        lambda r: f'<td class="name">{esc(r["name"])[:58]}</td>',
        lambda r: f'<td class="tag">{esc(r["category"])}</td>',
        lambda r: f'<td class="r">{num(r["sold_count"])}</td>',
        lambda r: f'<td class="r bad">{r["rating"]:.2f}★</td>',
        lambda r: f'<td class="r">Rs {num(r["price"])}</td>',
    ])
    cheap_rows = product_rows(cheap, [
        lambda r: f'<td class="name">{esc(r["name"])[:58]}</td>',
        lambda r: f'<td class="tag">{esc(r["category"])}</td>',
        lambda r: f'<td class="r">Rs {num(r["price"])}</td>',
        lambda r: f'<td class="r strong">{num(r["sold_count"])}</td>',
        lambda r: f'<td class="r">{(r["rating"] or 0):.1f}★</td>',
    ])

    starters = [c["category"] for c in cats if verdict(c["avg_price"], c["sellers"])[0] == "start"]
    verdict_line = (
        "Start in " + ", ".join(f"<b>{esc(s)}</b>" for s in starters) +
        " — low stock cost, proven volume, and fragmented sellers (no one dominates)."
        if starters else
        "No clear low-capital category yet in this partial data — full crawl pending."
    )

    con.close()
    html_doc = TEMPLATE.format(
        accent=ACCENT,
        products=num(total_products), units=money(total_units),
        rev=money(total_rev), sellers=num(total_sellers), ncats=ncats,
        cat_rows=cat_rows, top_rows=top_rows, gap_rows=gap_rows,
        cheap_rows=cheap_rows, verdict_line=verdict_line,
    )
    with open(args.out, "w") as f:
        f.write(html_doc)
    print(f"wrote {args.out} ({total_products} products, {ncats} categories)")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daraz Market Opportunity</title>
<style>
:root{{
  --bg:#0E1116; --panel:#171B22; --panel2:#1E242D; --line:#28303B;
  --ink:#E6E9EF; --muted:#8B93A1; --accent:{accent};
  --good:#3FB984; --warn:#E0A83E; --bad:#E06A5E;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:40px 24px 80px}}
.mono{{font-family:ui-monospace,"SF Mono",Menlo,monospace}}
.r,.figs,td.r{{font-family:ui-monospace,"SF Mono",Menlo,monospace;
  font-variant-numeric:tabular-nums}}
header{{border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:32px}}
.eyebrow{{font-family:ui-monospace,monospace;font-size:12px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--accent);margin:0 0 10px}}
h1{{font-size:38px;line-height:1.05;margin:0;letter-spacing:-.02em;text-wrap:balance;font-weight:700}}
.sub{{color:var(--muted);margin:12px 0 0;max-width:60ch}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0 36px}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.kpi .n{{font-family:ui-monospace,monospace;font-size:26px;font-weight:600;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
.kpi .l{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-top:6px}}
.verdict{{background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:20px 22px;margin-bottom:40px}}
.verdict h2{{margin:0 0 8px;font-size:14px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent)}}
.verdict p{{margin:0;font-size:17px;line-height:1.5}}
section{{margin-bottom:40px}}
h3{{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);
  margin:0 0 4px;font-weight:600}}
.note{{color:var(--muted);font-size:13px;margin:0 0 14px}}
.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:10px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;min-width:560px}}
th{{text-align:left;font-family:ui-monospace,monospace;font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  padding:11px 12px;border-bottom:1px solid var(--line);background:var(--panel)}}
th.r,td.r{{text-align:right}}
td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:var(--panel)}}
td.name{{color:var(--ink);font-weight:500;max-width:340px}}
td.muted{{color:var(--muted)}}
td.strong{{color:var(--accent);font-weight:600}}
td.bad{{color:var(--bad)}}
.tag{{font-family:ui-monospace,monospace;font-size:11px;color:var(--muted);
  background:var(--panel2);padding:2px 7px;border-radius:5px;white-space:nowrap}}
td.figs{{white-space:nowrap}}
.bar{{height:5px;background:var(--panel2);border-radius:3px;margin-top:6px;overflow:hidden}}
.bar span{{display:block;height:100%;border-radius:3px}}
.bar .rev{{background:var(--accent)}}
.bar .sell{{background:#5B6675}}
.pill{{font-family:ui-monospace,monospace;font-size:11px;font-weight:600;
  padding:3px 9px;border-radius:20px;white-space:nowrap}}
.pill.start{{background:rgba(63,185,132,.14);color:var(--good);border:1px solid rgba(63,185,132,.3)}}
.pill.consider{{background:rgba(224,168,62,.14);color:var(--warn);border:1px solid rgba(224,168,62,.3)}}
.pill.hard{{background:rgba(224,106,94,.14);color:var(--bad);border:1px solid rgba(224,106,94,.3)}}
footer{{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:20px;margin-top:8px}}
@media(max-width:680px){{.kpis{{grid-template-columns:repeat(2,1fr)}} h1{{font-size:30px}}}}
</style></head>
<body><div class="wrap">
<header>
  <p class="eyebrow">Daraz.com.np · Market Intelligence</p>
  <h1>What sells in Nepal — and what you should sell</h1>
  <p class="sub">Cumulative sales, seller spread, and quality gaps across live Daraz
  category listings. <b>Demand Index</b> = price × <i>all-time</i> units sold — a popularity
  proxy in Rs, <b>not monthly revenue and not audited GMV</b>.</p>
</header>

<div class="kpis">
  <div class="kpi"><div class="n">{products}</div><div class="l">Products</div></div>
  <div class="kpi"><div class="n">{units}</div><div class="l">Units sold</div></div>
  <div class="kpi"><div class="n">Rs {rev}</div><div class="l">Demand Index (all-time)</div></div>
  <div class="kpi"><div class="n">{sellers}</div><div class="l">Distinct sellers</div></div>
</div>

<div class="verdict">
  <h2>The verdict</h2>
  <p>{verdict_line}</p>
</div>

<section>
  <h3>Category opportunity matrix</h3>
  <p class="note">Fewer sellers = easier entry. Lower avg price = less capital to start.</p>
  <div class="scroll"><table>
    <thead><tr><th>Category</th><th>Demand Index</th><th class="r">Units</th>
      <th class="r">Avg price</th><th>Sellers</th><th>Entry</th></tr></thead>
    <tbody>{cat_rows}</tbody>
  </table></div>
</section>

<section>
  <h3>Top products by demand</h3>
  <p class="note">The highest-revenue listings right now — exact products.</p>
  <div class="scroll"><table>
    <thead><tr><th>Product</th><th>Cat</th><th class="r">Price</th><th class="r">Sold</th>
      <th class="r">Demand idx</th><th class="r">Rating</th><th>Seller</th></tr></thead>
    <tbody>{top_rows}</tbody>
  </table></div>
</section>

<section>
  <h3>Demand gaps — sell it, do it better</h3>
  <p class="note">High volume despite weak ratings (&lt;4.4). Room to win on quality.</p>
  <div class="scroll"><table>
    <thead><tr><th>Product</th><th>Cat</th><th class="r">Sold</th>
      <th class="r">Rating</th><th class="r">Price</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table></div>
</section>

<section>
  <h3>Low-capital starters (under Rs 1,000)</h3>
  <p class="note">Cheap to stock, proven volume — where to test first.</p>
  <div class="scroll"><table>
    <thead><tr><th>Product</th><th>Cat</th><th class="r">Price</th>
      <th class="r">Sold</th><th class="r">Rating</th></tr></thead>
    <tbody>{cheap_rows}</tbody>
  </table></div>
</section>

<footer>Generated from a live Daraz crawl · {ncats} categories · sold-counts are
cumulative (all-time) popularity, not current velocity — re-crawl weekly to see what's rising.
Note: ~16% of listings have no rating yet; brand "generic" share is overstated in electronics
(Daraz mislabels some brands as "No Brand"). Demand Index is a price×units proxy, not audited revenue.</footer>
</div></body></html>
"""


if __name__ == "__main__":
    main()
