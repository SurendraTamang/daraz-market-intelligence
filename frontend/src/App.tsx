import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import type { Product } from "./types";
import { compact, int, rs } from "./format";
import { BRAND } from "./brand";
import { useData } from "./useData";

// Chart ink. Every chart is single-series, so one hue (the accent) carries the data;
// category identity is the axis label or tooltip, never a color (3,000+ categories can't be colored).
const INK = { grid: "#28303B", axis: "#8A93A3", data: "#F2A93B", dim: "#5A6372" };
const MIN_REVIEWS = 10;
// slugs come URL-encoded from Daraz ("d%c3%a9cor-wallpaper")
const cname = (slug: string) => { try { return decodeURIComponent(slug); } catch { return slug; } }; // a rating from fewer reviews is noise

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`font-mono text-xs px-2.5 py-1 rounded-full border transition-colors ${
        active
          ? "bg-accent/15 text-accent border-accent/40"
          : "bg-panel2 text-muted border-line hover:text-fg"
      }`}
    >
      {children}
    </button>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-panel border border-line rounded-xl px-5 py-4">
      <div className="font-mono text-2xl font-semibold tnum">{value}</div>
      <div className="text-muted text-[11px] uppercase tracking-wider mt-1">{label}</div>
      {sub && <div className="text-muted text-[11px] mt-0.5">{sub}</div>}
    </div>
  );
}

function Panel({ title, note, children, className = "" }: {
  title: string; note?: string; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`bg-panel border border-line rounded-xl p-5 ${className}`}>
      <h3 className="text-[13px] uppercase tracking-wider text-muted font-semibold">{title}</h3>
      {note && <p className="text-muted text-xs mt-0.5 mb-3">{note}</p>}
      {!note && <div className="mb-3" />}
      {children}
    </section>
  );
}

function Tip({ active, payload, render }: {
  active?: boolean; payload?: { payload: any }[]; render: (d: any) => React.ReactNode;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-panel2 border border-line rounded-lg px-3 py-2 text-xs shadow-lg max-w-[280px]">
      {render(payload[0].payload)}
    </div>
  );
}

const median = (xs: number[]) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};

const LEVERS: [keyof Product["levers"], string][] = [
  ["demand", "Demand"], ["competition", "Few sellers"], ["quality", "Rating gap"], ["afford", "Cheap"],
];

function LeverBars({ p }: { p: Product }) {
  return (
    <div className="flex gap-2" aria-label="score drivers">
      {LEVERS.map(([k, label]) => (
        <div key={k} title={`${label}: ${(p.levers[k] * 100).toFixed(0)}th percentile`} className="w-12">
          <div className="h-1.5 bg-panel2 rounded-full overflow-hidden">
            <div className="h-full bg-fg/60 rounded-full" style={{ width: `${p.levers[k] * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

const axis = { stroke: INK.axis, fontSize: 11, tickLine: false };

export default function App() {
  const { data, live } = useData();
  const CATS = useMemo(() => data.categories.map((c) => c.category).sort(), [data]);

  const [cat, setCat] = useState("");
  const [maxPrice, setMaxPrice] = useState(2000);
  const [minSold, setMinSold] = useState(500);
  const [brand, setBrand] = useState<"all" | "generic" | "branded">("all");
  const [search, setSearch] = useState("");
  const pickedCat = CATS.includes(cat) ? cat : "";

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return data.products.filter(
      (p) =>
        (!pickedCat || p.category === pickedCat) &&
        p.price <= maxPrice &&
        p.sold >= minSold &&
        (brand === "all" || (brand === "generic" ? p.generic : !p.generic)) &&
        (!q || p.name.toLowerCase().includes(q)),
    );
  }, [data, pickedCat, maxPrice, minSold, brand, search]);

  const kpis = useMemo(() => {
    const units = filtered.reduce((s, p) => s + p.sold, 0);
    const revenue = filtered.reduce((s, p) => s + p.revenue, 0);
    const generic = filtered.reduce((s, p) => s + (p.generic ? p.sold : 0), 0);
    const sellers = new Set(filtered.map((p) => p.seller)).size;
    return { count: filtered.length, units, revenue, sellers, genericPct: units ? (100 * generic) / units : 0 };
  }, [filtered]);

  // top 15 categories inside the current filter; the rest is a long tail
  const catAgg = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of filtered) m.set(p.category, (m.get(p.category) ?? 0) + p.revenue);
    return [...m.entries()].map(([category, revenue]) => ({ category, revenue }))
      .sort((a, b) => b.revenue - a.revenue).slice(0, 15);
  }, [filtered]);

  // competition map: every category from the full rollup, not just the shipped product slice
  const catMap = useMemo(() => {
    const pts = data.categories.filter((c) => c.units > 0 && c.sellers > 0 && c.products >= 5);
    return { pts, mx: median(pts.map((c) => c.sellers)), my: median(pts.map((c) => c.units)) };
  }, [data]);

  const scatterPts = useMemo(() => filtered.filter((p) => p.sold > 0 && p.price > 0), [filtered]);

  const gaps = useMemo(
    () => filtered.filter((p) => p.rating > 0 && p.rating < 4.4 && p.reviews >= MIN_REVIEWS)
      .sort((a, b) => b.sold - a.sold).slice(0, 10),
    [filtered],
  );

  const top = filtered.slice(0, 25);

  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8">
      {/* header */}
      <header className="border-b border-line pb-6 mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-accent text-lg">{BRAND.logo}</span>
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-accent">
            {BRAND.eyebrow}
          </span>
          {live && (
            <span className="font-mono text-[10px] uppercase tracking-wider text-good border border-good/40 bg-good/10 rounded-full px-2 py-0.5">
              ● live
            </span>
          )}
        </div>
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-balance">
          {BRAND.headline}
        </h1>
        <p className="text-muted mt-2 max-w-3xl text-sm">
          {data.meta.run && <>Snapshot <span className="text-fg font-mono">{data.meta.run}</span> · </>}
          {int(data.meta.products)} products scored · {int(data.meta.categories)} categories ·{" "}
          {int(data.meta.sellers)} sellers. {BRAND.tagline}
        </p>
      </header>

      {/* filters */}
      <div className="bg-panel border border-line rounded-xl p-4 mb-6 flex flex-wrap gap-x-8 gap-y-4 items-end">
        <div className="flex flex-col gap-1 min-w-[220px]">
          <label htmlFor="cat" className="text-[11px] uppercase tracking-wider text-muted">
            Category <span className="normal-case">({int(CATS.length)})</span>
          </label>
          <div className="flex gap-1.5">
            <input id="cat" list="cats" value={cat} onChange={(e) => setCat(e.target.value)}
              placeholder="all categories"
              className="bg-panel2 border border-line rounded-md px-3 py-1.5 text-sm font-mono outline-none focus:border-accent/60 w-56" />
            {cat && <button onClick={() => setCat("")} className="text-muted hover:text-fg text-xs px-2">clear</button>}
          </div>
          <datalist id="cats">{CATS.map((c) => <option key={c} value={c}>{cname(c)}</option>)}</datalist>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wider text-muted">
            Max price <span className="text-fg font-mono">Rs {int(maxPrice)}</span>
          </label>
          <input type="range" min={100} max={8000} step={100} value={maxPrice}
            onChange={(e) => setMaxPrice(+e.target.value)} className="w-40 accent-accent" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wider text-muted">
            Min sold <span className="text-fg font-mono">{int(minSold)}</span>
          </label>
          <input type="range" min={0} max={5000} step={100} value={minSold}
            onChange={(e) => setMinSold(+e.target.value)} className="w-40 accent-accent" />
        </div>
        <div className="flex flex-col gap-2">
          <label className="text-[11px] uppercase tracking-wider text-muted">Brand</label>
          <div className="flex gap-1.5">
            {(["all", "generic", "branded"] as const).map((b) => (
              <Chip key={b} active={brand === b} onClick={() => setBrand(b)}>{b}</Chip>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1 flex-1 min-w-[160px]">
          <label className="text-[11px] uppercase tracking-wider text-muted">Search</label>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="product name…"
            className="bg-panel2 border border-line rounded-md px-3 py-1.5 text-sm outline-none focus:border-accent/60" />
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="Products" value={int(kpis.count)} sub="match filters (top 5,000 by score)" />
        <Stat label="Units sold" value={compact(kpis.units)} sub="Daraz recent-sales window" />
        <Stat label="Demand Index" value={rs(kpis.revenue)} sub="price × units, not revenue" />
        <Stat label="Sellers" value={int(kpis.sellers)} />
        <Stat label="Generic share" value={`${kpis.genericPct.toFixed(0)}%`} sub="of units, “No Brand”" />
      </div>

      {kpis.count === 0 ? (
        <div className="bg-panel border border-line rounded-xl p-10 text-center text-muted">
          No products match these filters. Loosen them.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* opportunity leaderboard */}
          <Panel title="Top opportunities" note="Ranked by Opportunity Score. Bars show each driver as a percentile across all scored products."
            className="lg:col-span-2">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[860px]">
                <thead>
                  <tr className="text-muted font-mono text-[11px] uppercase tracking-wider text-left">
                    <th className="py-2 pr-3 font-semibold text-right">Score</th>
                    <th className="py-2 px-3 font-semibold">Product</th>
                    <th className="py-2 px-3 font-semibold">Category</th>
                    <th className="py-2 px-3 font-semibold text-right">Price</th>
                    <th className="py-2 px-3 font-semibold text-right">Sold</th>
                    <th className="py-2 px-3 font-semibold text-right">Rating (n)</th>
                    <th className="py-2 px-3 font-semibold normal-case tracking-normal">Demand · Few sellers · Rating gap · Cheap</th>
                  </tr>
                </thead>
                <tbody>
                  {top.map((p, i) => (
                    <tr key={i} className="border-t border-line hover:bg-panel2/60">
                      <td className="py-2 pr-3 text-right font-mono text-xs text-accent tnum">{p.score.toFixed(2)}</td>
                      <td className="py-2 px-3 max-w-[300px] truncate" title={p.name}>{p.name}</td>
                      <td className="py-2 px-3 font-mono text-[11px] text-muted max-w-[160px] truncate">{cname(p.category)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">Rs {int(p.price)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">{int(p.sold)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">
                        {p.rating ? p.rating.toFixed(1) : "–"} <span className="text-muted">({int(p.reviews)})</span>
                      </td>
                      <td className="py-2 px-3"><LeverBars p={p} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* competition map */}
          <Panel title="Category competition map"
            note={`Each dot is a category (≥5 products). Top-left = demand with few sellers. Lines at the medians. Log scales.`}>
            <ResponsiveContainer width="100%" height={320}>
              <ScatterChart margin={{ left: 4, right: 12, top: 8, bottom: 16 }}>
                <CartesianGrid stroke={INK.grid} />
                <XAxis type="number" dataKey="sellers" scale="log" domain={["auto", "auto"]} {...axis}
                  label={{ value: "sellers in category", position: "insideBottom", offset: -8, fill: INK.axis, fontSize: 11 }} />
                <YAxis type="number" dataKey="units" scale="log" domain={["auto", "auto"]} tickFormatter={compact} {...axis}
                  label={{ value: "units sold", angle: -90, position: "insideLeft", fill: INK.axis, fontSize: 11 }} />
                <ZAxis range={[24, 24]} />
                <ReferenceLine x={catMap.mx} stroke={INK.axis} strokeDasharray="3 3" />
                <ReferenceLine y={catMap.my} stroke={INK.axis} strokeDasharray="3 3" />
                <Tooltip cursor={false} content={<Tip render={(c) => (
                  <>
                    <div className="font-mono text-fg">{cname(c.category)}</div>
                    <div className="text-muted">{int(c.units)} units · {c.sellers} sellers · avg Rs {int(c.avgPrice)}</div>
                  </>
                )} />} />
                <Scatter data={catMap.pts} fill={INK.data} fillOpacity={0.35} isAnimationActive={false}
                  shape={(s: any) => (
                    <circle cx={s.cx} cy={s.cy} r={s.payload.category === pickedCat ? 7 : 3.5}
                      fill={s.payload.category === pickedCat ? INK.data : pickedCat ? INK.dim : INK.data}
                      fillOpacity={s.payload.category === pickedCat ? 1 : 0.35}
                      stroke={s.payload.category === pickedCat ? "#141922" : "none"} strokeWidth={2} />
                  )} />
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          {/* price vs demand */}
          <Panel title="Price vs units sold" note="Each dot is a product matching the filters. Log scales; demand is heavy-tailed.">
            <ResponsiveContainer width="100%" height={320}>
              <ScatterChart margin={{ left: 4, right: 12, top: 8, bottom: 16 }}>
                <CartesianGrid stroke={INK.grid} />
                <XAxis type="number" dataKey="price" scale="log" domain={["auto", "auto"]} tickFormatter={compact} {...axis}
                  ticks={[20, 50, 100, 200, 500, 1000, 2000, 5000].filter((t) => t <= maxPrice)}
                  label={{ value: "price (Rs)", position: "insideBottom", offset: -8, fill: INK.axis, fontSize: 11 }} />
                <YAxis type="number" dataKey="sold" scale="log" domain={["auto", "auto"]} tickFormatter={compact} {...axis}
                  label={{ value: "units sold", angle: -90, position: "insideLeft", fill: INK.axis, fontSize: 11 }} />
                <ZAxis range={[20, 20]} />
                <Tooltip cursor={false} content={<Tip render={(p: Product) => (
                  <>
                    <div className="text-fg line-clamp-2">{p.name}</div>
                    <div className="text-muted font-mono">Rs {int(p.price)} · {int(p.sold)} sold · {cname(p.category)}</div>
                  </>
                )} />} />
                <Scatter data={scatterPts} fill={INK.data} fillOpacity={0.35} isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          {/* category demand */}
          <Panel title="Top 15 categories by Demand Index" note="Within the current filters. Demand Index = price × units, a popularity proxy, not revenue.">
            <ResponsiveContainer width="100%" height={Math.max(160, catAgg.length * 24 + 40)}>
              <BarChart data={catAgg} layout="vertical" margin={{ left: 4, right: 16 }} barCategoryGap={2}>
                <CartesianGrid horizontal={false} stroke={INK.grid} />
                <XAxis type="number" tickFormatter={(v) => compact(v)} {...axis} />
                <YAxis type="category" dataKey="category" width={180} {...axis} interval={0} tickFormatter={cname} />
                <Tooltip cursor={{ fill: "#ffffff08" }} content={<Tip render={(c) => (
                  <><div className="font-mono text-fg">{cname(c.category)}</div><div className="text-muted">{rs(c.revenue)} Demand Index</div></>
                )} />} />
                <Bar dataKey="revenue" fill={INK.data} radius={[0, 4, 4, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          {/* demand gaps */}
          <Panel title="Demand gaps" note={`High sales but rating below 4.4 (≥${MIN_REVIEWS} reviews). Room to win on quality.`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[480px]">
                <thead>
                  <tr className="text-muted font-mono text-[11px] uppercase tracking-wider text-left">
                    <th className="py-2 pr-3 font-semibold">Product</th>
                    <th className="py-2 px-3 font-semibold text-right">Sold</th>
                    <th className="py-2 px-3 font-semibold text-right">Rating (n)</th>
                    <th className="py-2 px-3 font-semibold text-right">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {gaps.map((p, i) => (
                    <tr key={i} className="border-t border-line hover:bg-panel2/60">
                      <td className="py-2 pr-3 max-w-[260px]">
                        <div className="truncate" title={p.name}>{p.name}</div>
                        <div className="font-mono text-[10px] text-muted truncate">{cname(p.category)}</div>
                      </td>
                      <td className="py-2 px-3 text-right font-mono tnum">{int(p.sold)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">
                        {p.rating.toFixed(1)} <span className="text-muted">({int(p.reviews)})</span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono tnum">Rs {int(p.price)}</td>
                    </tr>
                  ))}
                  {!gaps.length && (
                    <tr><td colSpan={4} className="py-6 text-center text-muted">No low-rated products with enough reviews in this filter.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      <footer className="text-muted text-xs border-t border-line pt-5 mt-8 leading-relaxed">
        Source: daily crawl of Daraz.com.np category listing pages (robots.txt-allowed URLs only, no personal data).
        "Units sold" is Daraz's own sold counter, a rolling recent window, not lifetime sales.
        Demand Index = price × units: a popularity proxy, not audited revenue. Ratings from fewer than
        {" "}{MIN_REVIEWS} reviews are not used for demand gaps. About 97% of listings say "No Brand", and some are
        mislabelled real brands, so the generic share is an upper bound.
      </footer>
    </div>
  );
}
