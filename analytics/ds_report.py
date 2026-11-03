#!/usr/bin/env python3
"""Data-science market report for the latest run -> one self-contained HTML page.

    python -m analytics.ds_report            # -> reports/market_report_<run>.html

Analysis on page-1 listings (equal depth for every category):
  1 coverage & data quality      4 price vs demand (rank correlation, price bands)
  2 demand concentration (Lorenz, Gini, top-k share)   5 quality gap (big sellers, weak ratings)
  3 market structure: HHI per niche (US DOJ/FTC bands)  6 robustness: Monte Carlo over score weights
  7 uncertainty: bootstrap CIs for the top niches      -> recommendations that survive 6 and 7
Charts: plotly (plotly.js from jsdelivr). Seeded RNG, so the same data gives the same report.
"""
import datetime
import html
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analytics.analyze import MIN_REVIEWS, WEIGHTS, latest_run, load_rows, score_rows
from daraz import db

RNG = np.random.default_rng(42)
PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js"
LEVERS = ["demand", "competition", "quality", "afford", "generic"]   # velocity: no history yet
MC_DRAWS, BOOT_DRAWS, TOP_K, MIN_NICHE = 300, 1000, 20, 8
HHI_BANDS = [(0, 1500, "Unconcentrated"), (1500, 2500, "Moderately concentrated"),
             (2500, 10001, "Highly concentrated")]                    # 2023 Merger Guidelines use 1000/1800; see note
BANDS = [(0, 200, "< Rs 200"), (200, 500, "Rs 200–500"), (500, 1000, "Rs 500–1k"),
         (1000, 2500, "Rs 1k–2.5k"), (2500, 5000, "Rs 2.5k–5k"), (5000, 10**12, "Rs 5k+")]
ACCENT, MUTED, WARN, BAD = "#0e7c74", "#9aa3b2", "#c48a1c", "#c2412d"


# ---------------------------------------------------------------- data
def load():
    con = db.connect_ro()
    run = latest_run(con)
    rows = score_rows(load_rows(con))                           # page 1, price > 0, sold > 0
    allp = pd.read_sql(
        "SELECT sold_count, rating, review_count, brand FROM products_dedup WHERE scraped_at = ? "
        "AND json_extract(raw_json, '$._page') = 1", con, params=(run,))
    status = dict(con.execute("SELECT status, COUNT(DISTINCT category) FROM crawl_log WHERE run_id = ? "
                              "AND page = 1 GROUP BY status", (run,)).fetchall())
    status["_all_products"], status["_all_with_sales"], status["_deep_cats"] = con.execute(
        "SELECT COUNT(DISTINCT nid), COUNT(DISTINCT CASE WHEN sold_count > 0 THEN nid END), "
        "(SELECT COUNT(DISTINCT category) FROM crawl_log WHERE run_id = ? AND page > 1 AND status = 'ok') "
        "FROM products WHERE scraped_at = ?", (run, run)).fetchone()
    con.close()
    p = pd.DataFrame([{**{k: r[k] for k in ("nid", "name", "category", "price", "sold_count", "rating",
                                              "review_count", "seller_id", "seller_name", "url", "score")},
                       **{f"l_{k}": r["levers"][k] for k in LEVERS}} for r in rows])
    p["seller"] = p["seller_id"].fillna("nid:" + p["nid"].astype(str))
    p["review_count"] = p["review_count"].fillna(0)
    return run, p, allp, status


def niche_table(p):
    g = p.groupby("category")
    t = pd.DataFrame({"units": g["sold_count"].sum(), "products": g.size(),
                      "sellers": g["seller"].nunique(), "median_price": g["price"].median()})
    su = p.groupby(["category", "seller"])["sold_count"].sum()
    share = su / su.groupby(level=0).transform("sum")
    t["hhi"] = (share.pow(2).groupby(level=0).sum() * 10000).round()
    t["top1"] = share.groupby(level=0).max()
    rated = p[(p.review_count >= MIN_REVIEWS) & p.rating.notna()]
    t["rating"] = rated.groupby("category")["rating"].mean()
    return t


def niche_scores(p, s):
    """Niche score = units-weighted mean of its top-20 product scores (same rule as analyze.niches)."""
    d = pd.DataFrame({"category": p["category"].values, "s": s, "u": p["sold_count"].values})
    d = d.sort_values(["category", "s"], ascending=[True, False])
    d = d[d.groupby("category").cumcount() < 20]
    num = (d.s * d.u).groupby(d.category).sum()
    return num / d.u.groupby(d.category).sum().replace(0, 1)


def monte_carlo(p, eligible):
    L = p[[f"l_{k}" for k in LEVERS]].to_numpy()
    gate = 0.4 + 0.6 * p["l_demand"].to_numpy()
    base_w = np.array([WEIGHTS[k] for k in LEVERS])
    base_w = base_w / base_w.sum()
    ranks = []
    for _ in range(MC_DRAWS):
        w = RNG.dirichlet(base_w * 40)                          # ~±35% around each default weight
        ns = niche_scores(p, (L @ w) * gate)
        ns = ns[ns.index.isin(eligible)]
        ranks.append(ns.rank(ascending=False, method="first"))
    R = pd.concat(ranks, axis=1)
    return pd.DataFrame({"p_top": (R <= TOP_K).mean(axis=1), "rank_med": R.median(axis=1),
                         "rank_lo": R.quantile(0.05, axis=1), "rank_hi": R.quantile(0.95, axis=1)})


def bootstrap(p, cats):
    out = {}
    for c in cats:
        d = p[p.category == c]
        u, s, pr = d["sold_count"].to_numpy(), d["seller"].to_numpy(), d["price"].to_numpy()
        top1, med = [], []
        for _ in range(BOOT_DRAWS):
            i = RNG.integers(0, len(d), len(d))
            t = pd.Series(u[i]).groupby(s[i]).sum()
            top1.append(t.max() / max(t.sum(), 1))
            med.append(np.median(pr[i]))
        out[c] = {"top1_lo": np.quantile(top1, .05), "top1_hi": np.quantile(top1, .95),
                  "price_lo": np.quantile(med, .05), "price_hi": np.quantile(med, .95)}
    return pd.DataFrame(out).T


# ---------------------------------------------------------------- presentation helpers
def fmt(n, d=0):
    return f"{n:,.{d}f}"


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def label(slug):
    return slug.replace("%c3%a9", "é").replace("-", " ").strip().capitalize()


def style(fig, h=380):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=12, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="IBM Plex Sans, sans-serif", size=12,
                      color="#7d8796"), showlegend=False, hoverlabel=dict(font_family="IBM Plex Sans"))
    fig.update_xaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False, linecolor="rgba(128,128,128,.4)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False)
    return fig


def chart(fig, cid):
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=cid,
                       config={"displayModeBar": False, "responsive": True})


def table(df, cols, num=()):
    head = "".join(f'<th class="{"n" if c in num else ""}">{html.escape(h)}</th>' for c, h in cols)
    body = "".join("<tr>" + "".join(f'<td class="{"n" if c in num else ""}">{v}</td>' for c, v in
                   ((c, r[c]) for c, _ in cols)) + "</tr>" for r in df.to_dict("records"))
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


# ---------------------------------------------------------------- report
def main():
    run, p, allp, status = load()
    nt = niche_table(p)
    elig = nt[nt.products >= MIN_NICHE].index
    base = niche_scores(p, p["score"].to_numpy())
    base = base[base.index.isin(elig)].sort_values(ascending=False)
    nt["score"] = base

    # 1 coverage & quality
    live, dead, empty = status.get("ok", 0), status.get("not_found", 0) + status.get("moved", 0), status.get("empty", 0)
    listed = len(allp)
    with_sales = (allp.sold_count > 0).mean()
    rated = allp.rating.notna().mean()
    no_brand = allp.brand.fillna("").str.strip().str.lower().isin(["no brand", ""]).mean()

    # 2 demand concentration
    u = np.sort(p.sold_count.to_numpy())[::-1]
    cum = np.cumsum(u) / u.sum()
    top = {k: cum[max(int(len(u) * k) - 1, 0)] for k in (0.01, 0.10, 0.20)}
    lor_x = np.linspace(0, 1, 201)
    lor_y = np.interp(lor_x, np.arange(1, len(u) + 1) / len(u), np.cumsum(u[::-1]) / u.sum())
    gini = 1 - 2 * np.trapezoid(lor_y, lor_x)

    # 3 structure
    nte = nt.loc[elig].copy()
    nte["band"] = pd.cut(nte.hhi, [b[0] for b in HHI_BANDS] + [10001], labels=[b[2] for b in HHI_BANDS], right=False)
    band_share = nte.band.value_counts(normalize=True).reindex([b[2] for b in HHI_BANDS])
    big = nte.units >= nte.units.median()
    open_big = nte[big & (nte.hhi < 1500)]

    # 4 price
    rho = p[["price", "sold_count"]].rank().corr().iloc[0, 1]
    bands = []
    for lo, hi, name in BANDS:
        d = p[(p.price >= lo) & (p.price < hi)]
        bands.append({"band": name, "units": d.sold_count.sum(), "products": len(d),
                      "median_sold": d.sold_count.median() if len(d) else 0})
    bands = pd.DataFrame(bands)

    # 5 quality gap
    q90 = p.sold_count.quantile(0.9)
    topd = p[(p.sold_count >= q90) & (p.review_count >= MIN_REVIEWS) & p.rating.notna()]
    weak = topd[topd.rating < 4.0].sort_values("sold_count", ascending=False)
    review_rate = (p[p.sold_count >= 100].review_count / p[p.sold_count >= 100].sold_count).median()

    # 6 robustness, 7 uncertainty
    mc = monte_carlo(p, elig)
    top_base = list(base.index[:TOP_K])
    boot = bootstrap(p, top_base[:15])
    robust = mc.loc[top_base].query("p_top >= 0.8").index.tolist()
    recs = nte.loc[[c for c in top_base if c in robust]].assign(
        p_top=mc.p_top, rank_lo=mc.rank_lo, rank_hi=mc.rank_hi).head(10)

    # ---------------- charts
    f_lor = go.Figure([go.Scatter(x=lor_x, y=lor_x, line=dict(color=MUTED, dash="dot", width=1), hoverinfo="skip"),
                       go.Scatter(x=lor_x, y=lor_y, line=dict(color=ACCENT, width=2.5), fill="tonexty",
                                  fillcolor="rgba(14,124,116,.10)",
                                  hovertemplate="Bottom %{x:.0%} of products → %{y:.1%} of units<extra></extra>")])
    style(f_lor, 340).update_xaxes(tickformat=".0%", title="share of products (fewest sales first)")
    f_lor.update_yaxes(tickformat=".0%", title="share of units sold")

    colors = np.where((nte.hhi < 1500) & big, ACCENT, np.where(nte.hhi >= 2500, BAD, MUTED))
    f_map = go.Figure(go.Scattergl(
        x=nte.units, y=nte.hhi, mode="markers", marker=dict(size=6, color=colors, opacity=.75),
        text=[label(c) for c in nte.index],
        customdata=np.stack([nte.sellers, nte.top1], axis=1),
        hovertemplate="<b>%{text}</b><br>%{x:,} units · %{customdata[0]} sellers<br>HHI %{y:,.0f} · "
                      "top seller %{customdata[1]:.0%}<extra></extra>"))
    for c in recs.index[:6]:
        f_map.add_annotation(x=np.log10(nte.units[c]), y=nte.hhi[c], text=label(c)[:24], showarrow=True,
                             arrowhead=0, arrowcolor=ACCENT, ax=28, ay=-22, font=dict(size=11, color=ACCENT))
    for y0, nm in ((1500, "1,500"), (2500, "2,500")):
        f_map.add_hline(y=y0, line=dict(color=MUTED, dash="dash", width=1),
                        annotation_text=f"HHI {nm}", annotation_position="top left",
                        annotation_font=dict(size=10, color="#7d8796"))
    f_map.add_vline(x=nte.units.median(), line=dict(color=MUTED, dash="dot", width=1))
    style(f_map, 440).update_xaxes(type="log", title="units sold in niche, Daraz count (page 1, log scale)")
    f_map.update_yaxes(title="HHI (seller concentration)", range=[0, 10200])

    f_price = go.Figure([go.Bar(x=bands.band, y=bands.units, marker_color=ACCENT, marker_cornerradius=4,
                                hovertemplate="%{x}<br>%{y:,} units<extra></extra>"),
                         go.Scatter(x=bands.band, y=bands.median_sold, yaxis="y2", mode="lines+markers",
                                    line=dict(color=WARN, width=2), marker=dict(size=7),
                                    hovertemplate="median %{y:,} sold per product<extra></extra>")])
    style(f_price, 340).update_layout(yaxis=dict(title="units sold"),
                                      yaxis2=dict(title="median sold per product", overlaying="y", side="right",
                                                  showgrid=False))

    mcs = mc.loc[top_base].assign(name=[label(c) for c in top_base])[::-1]
    f_mc = go.Figure([go.Scatter(x=mcs.rank_med, y=mcs.name, mode="markers",
                                 marker=dict(size=9, color=[ACCENT if v >= .8 else MUTED for v in mcs.p_top]),
                                 error_x=dict(type="data", symmetric=False, array=mcs.rank_hi - mcs.rank_med,
                                              arrayminus=mcs.rank_med - mcs.rank_lo, color="rgba(128,128,128,.55)",
                                              thickness=1.5, width=0),
                                 customdata=mcs.p_top,
                                 hovertemplate="%{y}<br>median rank %{x:.0f} · in top 20 in %{customdata:.0%} "
                                               "of weightings<extra></extra>")])
    style(f_mc, 560).update_xaxes(title="rank across 300 weightings (dot = median, bar = 90% range)",
                                  autorange="reversed")
    f_mc.update_yaxes(automargin=True)

    # ---------------- tables
    rec_tbl = recs.assign(
        niche=[f'<a href="https://www.daraz.com.np/{html.escape(c)}/" target="_blank" rel="noopener">'
               f'{html.escape(label(c))}</a>' for c in recs.index],
        u=recs.units.map(fmt), s=recs.sellers.map(fmt), h=recs.hhi.map(fmt),
        t1=recs.top1.map(pct), mp="Rs " + recs.median_price.map(fmt),
        r=recs.rating.map(lambda x: f"{x:.2f}★" if pd.notna(x) else "—"),
        rb=[f"{pct(v)} · #{lo:.0f}–{hi:.0f}" for v, lo, hi in zip(recs.p_top, recs.rank_lo, recs.rank_hi)])
    boot_tbl = boot.assign(
        niche=[html.escape(label(c)) for c in boot.index],
        t1=[f"{pct(nte.top1[c])} <span class='ci'>[{pct(boot.top1_lo[c])}–{pct(boot.top1_hi[c])}]</span>" for c in boot.index],
        mp=[f"Rs {fmt(nte.median_price[c])} <span class='ci'>[{fmt(boot.price_lo[c])}–{fmt(boot.price_hi[c])}]</span>"
            for c in boot.index],
        n=[fmt(nte.products[c]) for c in boot.index])
    w12 = weak.head(12)
    weak_tbl = w12.assign(
        prod=[f'<a href="{html.escape("https:" + u_ if str(u_).startswith("//") else str(u_))}" target="_blank" '
              f'rel="noopener">{html.escape(" ".join(str(n).split())[:64])}</a>'
              for n, u_ in zip(w12["name"], w12["url"])],
        niche=[html.escape(label(c)) for c in w12.category],
        pr="Rs " + w12.price.map(fmt), so=w12.sold_count.map(fmt),
        ra=w12.rating.map(lambda x: f"{x:.1f}★"), rv=w12.review_count.map(fmt))

    first = recs.index[0] if len(recs) else top_base[0]
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    ctx = dict(
        run=run, gen=gen, live=fmt(live), all_products=fmt(status["_all_products"]),
        all_with_sales=fmt(status["_all_with_sales"]), deep_cats=fmt(status["_deep_cats"]), dead=fmt(dead), empty=fmt(empty), listed=fmt(listed),
        with_sales=pct(with_sales), rated=pct(rated), no_brand=pct(no_brand), n=fmt(len(p)),
        niches=fmt(len(nt)), elig=fmt(len(elig)), min_niche=MIN_NICHE,
        top1=pct(top[0.01], 1), top10=pct(top[0.10]), top20=pct(top[0.20]), gini=f"{gini:.2f}",
        unconc=pct(band_share.iloc[0]), mod=pct(band_share.iloc[1]), high=pct(band_share.iloc[2]),
        open_big=fmt(len(open_big)), rho=f"{rho:+.2f}",
        struct_head=("Most niches have no dominant seller" if band_share.iloc[0] >= 0.5 else
                     "Most niches are concentrated, so the open ones are rare"),
        best_band=bands.loc[bands.units.idxmax(), "band"], best_band_share=pct(bands.units.max() / bands.units.sum()),
        weak_n=fmt(len(weak)), topd_n=fmt(len(topd)), weak_share=pct(len(weak) / max(len(topd), 1)),
        review_rate=pct(review_rate, 1), robust_n=len(robust), draws=MC_DRAWS, boot_n=fmt(BOOT_DRAWS),
        first=html.escape(label(first)), first_units=fmt(nte.units[first]), first_hhi=fmt(nte.hhi[first]),
        first_p=pct(mc.p_top[first]), q90=fmt(q90),
    )
    body = TEMPLATE.format(
        **ctx,
        lorenz=chart(f_lor, "c-lorenz"), nichemap=chart(f_map, "c-map"), price=chart(f_price, "c-price"),
        mc=chart(f_mc, "c-mc"),
        recs=table(rec_tbl, [("niche", "Niche"), ("u", "Units"), ("s", "Sellers"), ("h", "HHI"),
                             ("t1", "Top seller"), ("mp", "Median price"), ("r", "Rating"),
                             ("rb", "In top 20 · rank range")], num={"u", "s", "h", "t1", "mp", "r", "rb"}),
        boot=table(boot_tbl, [("niche", "Niche"), ("n", "Products"), ("t1", "Top-seller share [90% CI]"),
                              ("mp", "Median price [90% CI]")], num={"n", "t1", "mp"}),
        weak=table(weak_tbl, [("prod", "Product"), ("niche", "Niche"), ("pr", "Price"), ("so", "Sold"),
                              ("ra", "Rating"), ("rv", "Reviews")], num={"pr", "so", "ra", "rv"}),
    )
    os.makedirs("reports", exist_ok=True)
    out = f"reports/market_report_{run}.html"
    with open(out, "w") as f:
        f.write(HEAD + body)
    print(f"wrote {out}")


HEAD = f"""<title>Daraz Nepal Market Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<script src="{PLOTLY_JS}"></script>
<style>
:root {{ --bg:#f5f7f9; --panel:#ffffff; --ink:#152033; --muted:#5d6879; --rule:#dfe3ea; --accent:#0e7c74; --warn:#9a6a10; --bad:#b4372a; --chip:#e8f3f1; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#0f141a; --panel:#161d26; --ink:#e5eaf1; --muted:#98a3b4; --rule:#27313d; --accent:#3cb4a7; --warn:#e0ad55; --bad:#ef7d6c; --chip:#16302d; color-scheme: dark; }} }}
:root[data-theme="dark"] {{ --bg:#0f141a; --panel:#161d26; --ink:#e5eaf1; --muted:#98a3b4; --rule:#27313d; --accent:#3cb4a7; --warn:#e0ad55; --bad:#ef7d6c; --chip:#16302d; color-scheme: dark; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.6 "IBM Plex Sans", system-ui, sans-serif; padding-inline:16px; }}
.r {{ max-width:960px; margin:0 auto; padding-block:40px 64px; display:grid; gap:44px; }}
h1, h2 {{ font-family:"Source Serif 4", Georgia, serif; font-weight:600; text-wrap:balance; margin:0; }}
h1 {{ font-size:clamp(28px, 4.5vw, 42px); line-height:1.15; letter-spacing:-.01em; }}
h2 {{ font-size:23px; line-height:1.25; }}
h3 {{ font-size:13px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); margin:0 0 6px; font-weight:600; }}
p {{ margin:0; max-width:68ch; }}
.sec {{ display:grid; gap:14px; }}
.meta {{ color:var(--muted); font-size:13px; }}
.lead {{ font-size:17px; max-width:66ch; }}
.num, td.n, .stat b {{ font-family:"IBM Plex Mono", ui-monospace, monospace; font-variant-numeric:tabular-nums; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap:1px; background:var(--rule); border:1px solid var(--rule); border-radius:10px; overflow:hidden; }}
.stat {{ background:var(--panel); padding:16px 18px; display:grid; gap:4px; }}
.stat b {{ font-size:24px; font-weight:500; color:var(--ink); }}
.stat span {{ color:var(--muted); font-size:13px; line-height:1.4; }}
.find {{ border-left:3px solid var(--accent); padding:4px 0 4px 16px; display:grid; gap:6px; }}
.find.w {{ border-color:var(--warn); }}
.panel {{ background:var(--panel); border:1px solid var(--rule); border-radius:10px; padding:16px; }}
.cap {{ color:var(--muted); font-size:13px; margin-top:8px; }}
.tw {{ overflow-x:auto; border:1px solid var(--rule); border-radius:10px; background:var(--panel); }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
th {{ text-align:left; font-weight:600; color:var(--muted); font-size:12px; padding:10px 12px; border-bottom:1px solid var(--rule); white-space:nowrap; }}
td {{ padding:9px 12px; border-bottom:1px solid var(--rule); vertical-align:top; }}
tr:last-child td {{ border-bottom:0; }}
th.n, td.n {{ text-align:right; white-space:nowrap; }}
.ci {{ color:var(--muted); font-size:12px; }}
a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
a:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
ul {{ margin:0; padding-left:20px; display:grid; gap:6px; max-width:72ch; }}
.chip {{ display:inline-block; background:var(--chip); color:var(--accent); border-radius:999px; padding:1px 10px; font-size:12px; font-weight:600; }}
code {{ font-family:"IBM Plex Mono", monospace; font-size:.9em; }}
</style>
"""

TEMPLATE = """<main class="r">
<header class="sec">
  <span class="chip">Market report · snapshot {run}</span>
  <h1>Where a new seller can win on Daraz Nepal</h1>
  <p class="lead">From {n} products with sales across {niches} niches, the strongest opening is <b>{first}</b>:
  {first_units} units sold on page 1 with an HHI of {first_hhi}, and it stays in the top 20 under {first_p} of
  {draws} alternative scorings. {robust_n} of the top 20 niches are equally robust.</p>
  <p class="meta">Generated {gen} by <code>ds_report.py</code> from the project’s crawl database. All figures use
  page 1 of every category, so niches are compared at equal depth.</p>
</header>

<section class="stats" aria-label="Key figures">
  <div class="stat"><b>{live}</b><span>live categories crawled ({dead} dead links, {empty} empty)</span></div>
  <div class="stat"><b>{top1}</b><span>of all units sold come from the top 1% of products</span></div>
  <div class="stat"><b>{unconc}</b><span>of niches are unconcentrated (HHI &lt; 1,500)</span></div>
  <div class="stat"><b>{best_band}</b><span>price band with the most units ({best_band_share} of all)</span></div>
</section>

<section class="sec">
  <h2>1 · Data and how far to trust it</h2>
  <p>The crawler read every category in Daraz’s sitemap and followed {deep_cats} categories past page 1 for as long
  as their pages still showed sales: <b>{all_products} distinct products collected, {all_with_sales} of them with
  sales</b>. The analyses below use the {listed} page-1 listings only, so every niche is compared at the same depth;
  of those, {with_sales} show a sold count and {rated} have a rating. Prices and sold counts were spot-checked against the live
  site during the crawl’s quality gate.</p>
  <ul>
    <li><b>Daraz’s “X sold” behaves like a rolling recent window, not a lifetime total:</b> between daily snapshots
    5k+ listings’ counts fell, and out-of-season summer items fell steadily in October. So the counts track recent
    demand, and a week-over-week change measures acceleration. Counts are rounded above 1,000 (“2.7K sold”).</li>
    <li><b>Page 1 is a popularity-ranked sample</b> (top 40 per category). Niche totals understate big categories and
    favour established products.</li>
    <li><b>{no_brand} of listings say “No Brand”,</b> so brand is not used as evidence.</li>
    <li>Niches need at least {min_niche} products with sales to be ranked: {elig} qualify.</li>
  </ul>
</section>

<section class="sec">
  <h2>2 · Demand is extremely concentrated in a few products</h2>
  <div class="find"><p>The top 1% of products account for <b class="num">{top1}</b> of units, the top 10% for
  <b class="num">{top10}</b> and the top 20% for <b class="num">{top20}</b> (Gini {gini}). Winning a niche means
  displacing its few hero products, not matching the average listing.</p></div>
  <div class="panel">{lorenz}<p class="cap">Lorenz curve of units sold across products with sales. The further the
  curve bows from the dotted diagonal, the more sales concentrate in few products.</p></div>
</section>

<section class="sec">
  <h2>3 · {struct_head}</h2>
  <p>Seller concentration is measured with the Herfindahl–Hirschman Index: the sum of squared seller shares of a
  niche’s units, 0 to 10,000. Bands follow the classic US DOJ/FTC thresholds of 1,500 and 2,500. The 2023 Merger
  Guidelines lowered them to 1,000 and 1,800, so under the newer reading even fewer niches count as open. With 40 or
  fewer listings per niche, HHI also runs high for small niches: treat a single niche’s figure as indicative.</p>
  <div class="find"><p><b class="num">{unconc}</b> of niches are unconcentrated, <b class="num">{mod}</b> moderately
  and <b class="num">{high}</b> highly concentrated. <b class="num">{open_big}</b> niches are both above-median in
  demand and unconcentrated: the pool worth entering.</p></div>
  <div class="panel">{nichemap}<p class="cap">Every ranked niche. Teal: above-median demand and HHI under 1,500. Red:
  highly concentrated. Labels: the recommended niches. Hover for details.</p></div>
</section>

<section class="sec">
  <h2>4 · Cheap sells, but price alone does not predict demand</h2>
  <div class="find"><p>Units peak in <b>{best_band}</b> ({best_band_share} of all units). Across individual products
  the rank correlation between price and units sold is only <b class="num">{rho}</b> (Spearman): within a price band,
  product choice and listing quality matter far more than being cheapest. This is a cross-section, not a price
  elasticity: it cannot say what happens if you change your own price.</p></div>
  <div class="panel">{price}<p class="cap">Bars: units sold per price band. Line: median units per product in the
  band (right axis).</p></div>
</section>

<section class="sec">
  <h2>5 · A quality gap among the best sellers</h2>
  <div class="find w"><p>Of {topd_n} top-decile products (≥ {q90} sold) with at least 10 reviews, <b class="num">{weak_n}</b>
  ({weak_share}) rate below 4.0★. Buyers want the product but are not happy with what they get. A better-made version
  with an honest listing is the most direct way in. Roughly <b class="num">{review_rate}</b> of buyers leave a review.</p></div>
  {weak}
</section>

<section class="sec">
  <h2>6 · Which rankings survive a change of opinion</h2>
  <p>The opportunity score blends demand, competition, quality gap, affordability and brandlessness with fixed
  weights, and those weights are a judgement call. To test that, the niche ranking was recomputed under {draws}
  random weightings around the defaults (Dirichlet, about ±35% per weight).</p>
  <div class="panel">{mc}<p class="cap">Current top 20 niches. Dot: median rank across weightings; bar: 5th–95th
  percentile. Teal: in the top 20 under at least 80% of weightings.</p></div>
</section>

<section class="sec">
  <h2>7 · How precise the niche figures are</h2>
  <p>Each niche’s figures come from a sample of 40 or fewer listings, so they are uncertain. Bootstrap resampling
  ({boot_n} resamples per niche) gives 90% intervals for the two figures that drive the decision.</p>
  {boot}
</section>

<section class="sec">
  <h2>Recommendations</h2>
  <p>Niches in the current top 20 that stay there under at least 80% of weightings, with demand, competition and
  quality side by side. Start with the first, validate sourcing and margin on two or three, and let the daily
  velocity data confirm that demand is current, not historical.</p>
  {recs}
  <ul>
    <li><b>Validate by hand before buying stock:</b> landed cost and MOQ, margin of 2–3× after Daraz fees and ads, and
    whether the product shows well on video for your own channels.</li>
    <li><b>Watch velocity:</b> after a week of daily snapshots, re-run this report. A niche whose units are not
    growing is selling to the past.</li>
    <li><b>Use the quality gap:</b> the weakly rated best-sellers in section 5 are concrete products to improve on.</li>
  </ul>
</section>
</main>
"""

if __name__ == "__main__":
    main()
