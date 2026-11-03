export const rs = (n: number): string => {
  if (n >= 1e9) return `Rs ${(n / 1e9).toFixed(1)}B`;
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
