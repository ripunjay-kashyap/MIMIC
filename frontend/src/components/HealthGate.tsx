"use client";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

export function HealthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [initializing, setInitializing] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    let active = true;
    let poll: ReturnType<typeof setTimeout>;
    let failures = 0;
    const started = Date.now();
    const clock = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    async function check() {
      try {
        const health = await getHealth();
        if (!active) return;
        failures = 0;
        setInitializing(health.status === "ok" && !health.browser_ready);
        if (health.status === "ok" && health.browser_ready) {
          setReady(true); clearInterval(clock); return;
        }
      } catch { if (!active) return; failures++; setInitializing(false); }
      if (active) poll = setTimeout(check, Math.min(2000 + Math.max(0, failures - 1) * 1000, 5000));
    }
    void check();
    return () => { active = false; clearInterval(clock); clearTimeout(poll); };
  }, []);
  if (ready) return children;
  return <div className="gate"><section className="panel gate-card" role="status">
    <span className="eyebrow">Agent runtime</span>
    <h1>{initializing ? "Initializing browser workers…" : elapsed < 3 ? "Checking agent runtime…" : "Waking up agent runtime…"}</h1>
    {!initializing && elapsed >= 3 && <p>Free hosting can take ~30–60 s.</p>}
    <p className="timer">{elapsed} seconds elapsed</p><p className="muted">This page will open automatically when the runtime is ready.</p>
  </section></div>;
}
