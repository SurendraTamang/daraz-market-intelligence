export const rs = (n: number): string => {
  if (n >= 1e6) return `Rs ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `Rs ${(n / 1e3).toFixed(0)}K`;
  return `Rs ${Math.round(n)}`;
};

export const compact = (n: number): string => {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
};

export const int = (n: number): string => Math.round(n).toLocaleString();

// consistent color per category
const PALETTE = [
  "#F2A93B", "#3FB984", "#5B9BD5", "#E06A5E", "#B58BE0",
  "#E0A83E", "#4FBFA8", "#E07EA8", "#8FBF5B", "#6C79E0",
  "#D98C4A", "#54C1D6", "#C9A227", "#9B8CFF",
];
export const catColor = (cats: string[]): Record<string, string> =>
  Object.fromEntries(cats.map((c, i) => [c, PALETTE[i % PALETTE.length]]));
