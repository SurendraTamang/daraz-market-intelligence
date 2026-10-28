"""Daraz market-analysis app — interactive Opportunity Score.

    streamlit run app.py

Reads the DB READ-ONLY (safe while a crawl writes). Scores come from analyze.py (the one
scorer); sliders change the weights, filters narrow the list after scoring.
"""
import pandas as pd
import streamlit as st

from analyze import WEIGHTS, load_rows, score_rows
from daraz import db

st.set_page_config(page_title="Daraz Market Analyzer", page_icon="🛒", layout="wide")


@st.cache_data(ttl=60)
def load():
    # read-only so the app can never lock the DB the crawler writes
    con = db.connect_ro()
    rows = load_rows(con)
    con.close()
    return rows


try:
    rows = load()
except Exception as e:
    st.error(f"Can't read {db.path()}: {e}. Run a crawl first (see CLAUDE.md).")
    st.stop()

if not rows:
    st.warning("No rows yet — crawl still warming up. Refresh in a minute.")
    st.stop()

# ---------------- sidebar ----------------
st.sidebar.header("Score weights")
weights = {k: st.sidebar.slider(k.title(), 0.0, 1.0, v, 0.05) for k, v in WEIGHTS.items()}
scored = score_rows(rows, weights)
for r in scored:
    r.pop("levers", None)
df = pd.DataFrame(scored).rename(columns={"score": "opportunity"})

st.sidebar.header("Filters")
pick = st.sidebar.multiselect("Categories (empty = all)", sorted(df["category"].unique()))
pmax = int(df["price"].quantile(0.95))
max_price = st.sidebar.slider("Max price", 0, pmax, pmax, step=50)
min_sold = st.sidebar.slider("Min units sold (proven demand)", 0, 5000, 0, step=100)
brand_opt = st.sidebar.radio("Brand", ["All", "Generic only", "Branded only"], index=0)
min_rating = st.sidebar.slider("Min rating (0 keeps unrated)", 0.0, 5.0, 0.0, step=0.1)

f = df[(df["price"] <= max_price) & (df["sold_count"] >= min_sold)]
if pick:
    f = f[f["category"].isin(pick)]
if brand_opt == "Generic only":
    f = f[f["generic"]]
elif brand_opt == "Branded only":
    f = f[~f["generic"]]
f = f[f["rating"].fillna(0) >= min_rating]

# ---------------- header + KPIs ----------------
st.title("🛒 Daraz Market Analyzer")
st.caption("What to sell in Nepal — demand, velocity, competition, quality gaps. "
           "Est. revenue = price × lifetime sold (demand proxy).")

if f.empty:
    st.warning("No products match these filters. Loosen them.")
    st.stop()

k = st.columns(4)
k[0].metric("Products", f"{len(f):,}")
k[1].metric("Units sold", f"{int(f['sold_count'].sum()):,}")
k[2].metric("Est. revenue", f"Rs {f['est_revenue'].sum()/1e6:.1f}M")
k[3].metric("Sellers", f"{f['seller_id'].nunique():,}")

# ---------------- opportunity table ----------------
st.subheader("🎯 Top opportunities")
show = f.head(30)[["name", "category", "price", "sold_count", "units_per_week", "rating",
                   "est_revenue", "generic", "opportunity", "seller_name"]].copy()
st.dataframe(
    show, use_container_width=True, hide_index=True,
    column_config={
        "name": "Product", "category": "Cat",
        "price": st.column_config.NumberColumn("Price", format="Rs %d"),
        "sold_count": st.column_config.NumberColumn("Sold", format="%d"),
        "units_per_week": st.column_config.NumberColumn("Units/wk", format="%.0f"),
        "rating": st.column_config.NumberColumn("★", format="%.1f"),
        "est_revenue": st.column_config.NumberColumn("Est. rev", format="Rs %d"),
        "generic": "Generic", "seller_name": "Seller",
        "opportunity": st.column_config.ProgressColumn("Score", min_value=0, max_value=float(f["opportunity"].max())),
    },
)

# ---------------- charts ----------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("Revenue by category (top 25)")
    st.bar_chart(f.groupby("category")["est_revenue"].sum().sort_values(ascending=False).head(25))
with c2:
    st.subheader("Price vs demand")
    st.scatter_chart(f.head(2000), x="price", y="sold_count")

c3, c4 = st.columns(2)
with c3:
    st.subheader("Generic vs branded (units)")
    g = f.assign(kind=f["generic"].map({True: "Generic", False: "Branded"})) \
         .groupby("kind")["sold_count"].sum()
    st.bar_chart(g)
with c4:
    st.subheader("Demand gaps (≥10 reviews, rating < 4.4)")
    gaps = f[(f["review_count"].fillna(0) >= 10) & (f["rating"] < 4.4)].sort_values("sold_count", ascending=False)
    st.dataframe(gaps.head(12)[["name", "category", "sold_count", "rating", "price"]],
                 use_container_width=True, hide_index=True)
