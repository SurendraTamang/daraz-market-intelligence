import { useEffect, useState } from "react";
import bundled from "./data.json";
import type { Data } from "./types";

// If VITE_API_URL is set (dev/deploy with the FastAPI backend), fetch live data.
// Otherwise use the bundled snapshot — so the single-file/Artifact build works offline.
const API = import.meta.env.VITE_API_URL as string | undefined;

export function useData(): { data: Data; live: boolean; loading: boolean } {
  const [data, setData] = useState<Data>(bundled as unknown as Data);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(Boolean(API));

  useEffect(() => {
    if (!API) return;
    let ok = true;
    fetch(`${API}/api/data`)
      .then((r) => r.json())
      .then((d: Data) => {
        if (ok) { setData(d); setLive(true); }
      })
      .catch(() => { /* keep bundled fallback */ })
      .finally(() => ok && setLoading(false));
    return () => { ok = false; };
  }, []);

  return { data, live, loading };
}
