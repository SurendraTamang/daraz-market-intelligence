import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import type { Product } from "./types";
import { catColor, compact, int, rs } from "./format";
import { BRAND } from "./brand";
import { useData } from "./useData";

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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-panel border border-line rounded-xl px-5 py-4">
      <div className="font-mono text-2xl font-semibold tnum">{value}</div>
      <div className="text-muted text-[11px] uppercase tracking-wider mt-1">{label}</div>
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

function whyChips(p: Product): string[] {
  const w: string[] = [];
  if (p.levers.demand > 0.7) w.push("high demand");
  if (p.levers.afford > 0.7) w.push("cheap");
  if (p.levers.quality > 0.55) w.push("weak rivals");
  if (p.levers.competition > 0.6) w.push("few sellers");
  return w;
}

export default function App() {
  const { data, live } = useData();
  const CATS = useMemo(() => data.categories.map((c) => c.category), [data]);
  const COLOR = useMemo(() => catColor(CATS), [CATS]);

  const [picked, setPicked] = useState<Set<string>>(() => new Set(CATS));
  const maxPriceCap = 8000;
  const [maxPrice, setMaxPrice] = useState(2000);
  const [minSold, setMinSold] = useState(500);
  const [brand, setBrand] = useState<"all" | "generic" | "branded">("all");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return data.products.filter(
      (p) =>
        picked.has(p.category) &&
        p.price <= maxPrice &&
        p.sold >= minSold &&
        (brand === "all" || (brand === "generic" ? p.generic : !p.generic)) &&
        (!q || p.name.toLowerCase().includes(q)),
    );
  }, [data, picked, maxPrice, minSold, brand, search]);

  const kpis = useMemo(() => {
    const units = filtered.reduce((s, p) => s + p.sold, 0);
    const revenue = filtered.reduce((s, p) => s + p.revenue, 0);
    const sellers = new Set(filtered.map((p) => p.seller)).size;
    return { count: filtered.length, units, revenue, sellers };
  }, [filtered]);

  const catAgg = useMemo(() => {
    const m = new Map<string, { revenue: number; sellers: Set<string> }>();
    for (const p of filtered) {
      const e = m.get(p.category) ?? { revenue: 0, sellers: new Set<string>() };
      e.revenue += p.revenue;
      e.sellers.add(p.seller);
      m.set(p.category, e);
    }
    return [...m.entries()]
      .map(([category, e]) => ({ category, revenue: e.revenue, sellers: e.sellers.size }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [filtered]);

  const brandSplit = useMemo(() => {
    let g = 0, b = 0;
    for (const p of filtered) (p.generic ? (g += p.sold) : (b += p.sold));
    return [
      { name: "Generic", value: g, fill: "#3FB984" },
      { name: "Branded", value: b, fill: "#5B9BD5" },
    ];
  }, [filtered]);

  const gaps = useMemo(
    () => filtered.filter((p) => p.rating > 0 && p.rating < 4.4).sort((a, b) => b.sold - a.sold).slice(0, 10),
    [filtered],
  );

  const top = filtered.slice(0, 25);
  const maxScore = top[0]?.score ?? 1;

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
        <p className="text-muted mt-2 max-w-2xl text-sm">
          {int(data.meta.products)} products · {data.meta.categories} categories ·{" "}
          {int(data.meta.sellers)} sellers. {BRAND.tagline}
        </p>
      </header>

      {/* filters */}
      <div className="bg-panel border border-line rounded-xl p-4 mb-6 flex flex-wrap gap-x-8 gap-y-4 items-end">
        <div className="flex flex-col gap-2">
          <label className="text-[11px] uppercase tracking-wider text-muted">Categories</label>
          <div className="flex flex-wrap gap-1.5 max-w-xl">
            <Chip active={picked.size === CATS.length} onClick={() => setPicked(new Set(CATS))}>all</Chip>
            {CATS.map((c) => (
              <Chip
                key={c}
                active={picked.has(c)}
                onClick={() => {
                  const n = new Set(picked);
                  n.has(c) ? n.delete(c) : n.add(c);
                  setPicked(n.size ? n : new Set(CATS));
                }}
              >
                {c}
              </Chip>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wider text-muted">
            Max price <span className="text-fg font-mono">Rs {int(maxPrice)}</span>
          </label>
          <input type="range" min={100} max={maxPriceCap} step={100} value={maxPrice}
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="Products" value={int(kpis.count)} />
        <Stat label="Units sold" value={compact(kpis.units)} />
        <Stat label="Demand Index" value={rs(kpis.revenue)} />
        <Stat label="Sellers" value={int(kpis.sellers)} />
      </div>

      {kpis.count === 0 ? (
        <div className="bg-panel border border-line rounded-xl p-10 text-center text-muted">
          No products match these filters. Loosen them.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* opportunity leaderboard */}
          <Panel title="🎯 Top opportunities" note="Ranked by Opportunity Score — what to sell first"
            className="lg:col-span-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[720px]">
                <thead>
                  <tr className="text-muted font-mono text-[11px] uppercase tracking-wider text-left">
                    <th className="py-2 pr-3 font-semibold">Score</th>
                    <th className="py-2 pr-3 font-semibold">Product</th>
                    <th className="py-2 px-3 font-semibold">Cat</th>
                    <th className="py-2 px-3 font-semibold text-right">Price</th>
                    <th className="py-2 px-3 font-semibold text-right">Sold</th>
                    <th className="py-2 px-3 font-semibold text-right">★</th>
                    <th className="py-2 px-3 font-semibold">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {top.map((p, i) => (
                    <tr key={i} className="border-t border-line hover:bg-panel2/60">
                      <td className="py-2 pr-3 w-24">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-accent tnum w-8">{p.score.toFixed(2)}</span>
                          <div className="h-1.5 flex-1 bg-panel2 rounded-full overflow-hidden">
                            <div className="h-full bg-accent rounded-full"
                              style={{ width: `${Math.max(6, (p.score / maxScore) * 100)}%` }} />
                          </div>
                        </div>
                      </td>
                      <td className="py-2 pr-3 max-w-[320px] truncate">{p.name}</td>
                      <td className="py-2 px-3">
                        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded"
                          style={{ background: `${COLOR[p.category]}22`, color: COLOR[p.category] }}>
                          {p.category}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono tnum">Rs {int(p.price)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">{int(p.sold)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">{p.rating.toFixed(1)}</td>
                      <td className="py-2 px-3">
                        <div className="flex flex-wrap gap-1">
                          {whyChips(p).map((w) => (
                            <span key={w} className="text-[10px] font-mono text-muted bg-panel2 px-1.5 py-0.5 rounded">{w}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* category revenue */}
          <Panel title="Demand Index by category" note="Price × all-time units — a popularity proxy, not revenue" className="lg:col-span-2">
            <ResponsiveContainer width="100%" height={Math.max(220, catAgg.length * 26)}>
              <BarChart data={catAgg} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid horizontal={false} stroke="#28303B" />
                <XAxis type="number" tickFormatter={(v) => compact(v)} stroke="#8A93A3" fontSize={11} />
                <YAxis type="category" dataKey="category" width={110} stroke="#8A93A3" fontSize={11} />
                <Tooltip cursor={{ fill: "#ffffff08" }}
                  contentStyle={{ background: "#141922", border: "1px solid #28303B", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [rs(v), "Demand Index"]} />
                <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                  {catAgg.map((c) => <Cell key={c.category} fill={COLOR[c.category]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          {/* brand donut */}
          <Panel title="Generic vs branded" note="Share of units sold">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={brandSplit} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
                  {brandSplit.map((s) => <Cell key={s.name} fill={s.fill} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#141922", border: "1px solid #28303B", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number, n) => [`${compact(v)} units`, n]} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex justify-center gap-4 text-xs text-muted">
              {brandSplit.map((s) => (
                <span key={s.name} className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: s.fill }} />
                  {s.name}
                </span>
              ))}
            </div>
          </Panel>

          {/* price vs demand scatter */}
          <Panel title="Price vs demand" note="Where volume concentrates — find the sweet spot" className="lg:col-span-2">
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart margin={{ left: 8, right: 16, top: 8 }}>
                <CartesianGrid stroke="#28303B" />
                <XAxis type="number" dataKey="price" name="Price" tickFormatter={(v) => compact(v)}
                  stroke="#8A93A3" fontSize={11} domain={[0, 8000]} />
                <YAxis type="number" dataKey="sold" name="Sold" tickFormatter={(v) => compact(v)}
                  stroke="#8A93A3" fontSize={11} />
                <ZAxis range={[30, 30]} />
                <Tooltip cursor={{ strokeDasharray: "3 3", stroke: "#8A93A3" }}
                  contentStyle={{ background: "#141922", border: "1px solid #28303B", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number, n) => [n === "price" ? `Rs ${int(v)}` : int(v), n]}
                  labelFormatter={() => ""} />
                <Scatter data={filtered.filter((p) => p.price <= 8000)} fillOpacity={0.7}>
                  {filtered.filter((p) => p.price <= 8000).map((p, i) => (
                    <Cell key={i} fill={COLOR[p.category]} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          {/* demand gaps */}
          <Panel title="Demand gaps" note="High sales, weak rating (<4.4) — beat them on quality" className="lg:col-span-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead>
                  <tr className="text-muted font-mono text-[11px] uppercase tracking-wider text-left">
                    <th className="py-2 pr-3 font-semibold">Product</th>
                    <th className="py-2 px-3 font-semibold">Cat</th>
                    <th className="py-2 px-3 font-semibold text-right">Sold</th>
                    <th className="py-2 px-3 font-semibold text-right">Rating</th>
                    <th className="py-2 px-3 font-semibold text-right">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {gaps.map((p, i) => (
                    <tr key={i} className="border-t border-line hover:bg-panel2/60">
                      <td className="py-2 pr-3 max-w-[360px] truncate">{p.name}</td>
                      <td className="py-2 px-3">
                        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded"
                          style={{ background: `${COLOR[p.category]}22`, color: COLOR[p.category] }}>{p.category}</span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono tnum">{int(p.sold)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum text-bad">{p.rating.toFixed(2)}</td>
                      <td className="py-2 px-3 text-right font-mono tnum">Rs {int(p.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      <footer className="text-muted text-xs border-t border-line pt-5 mt-8">
        Live Daraz.com.np crawl · sold-counts are cumulative (all-time) popularity, not current
        velocity — re-crawl weekly to track what's rising. Demand Index = price × all-time units
        (a proxy, not audited revenue). ~16% of listings lack a rating; "generic" share is overstated
        in electronics (Daraz mislabels some brands). Built for market-entry decisions.
      </footer>
    </div>
  );
}
