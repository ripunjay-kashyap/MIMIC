"use client";
import { useEffect, useState } from "react";
export function useResource<T>(load: () => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean }>({ data: null, error: null, loading: true });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    load().then(data => { if (active) setState({ data, error: null, loading: false }); })
      .catch(error => { if (active) setState({ data: null, error, loading: false }); });
    return () => { active = false; };
  }, [load, version]);
  return { ...state, retry: () => { setState({ data: null, error: null, loading: true }); setVersion(v => v + 1); } };
}
