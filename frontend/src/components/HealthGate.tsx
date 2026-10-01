"use client";
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { getHealth } from "@/lib/api";
import { PersonaSprite, personaTypes } from "./PersonaSprite";

export function HealthGate({ children, brief }: { children: React.ReactNode; brief?: React.ReactNode }) {
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
  return <div className="gate"><section className="gate-card" role="status">
    <ul className="cast gate-cast" aria-hidden="true">
      {personaTypes.map((type, index) => <li key={type} style={{ "--i": index } as CSSProperties}><PersonaSprite type={type} size={52} /></li>)}
    </ul>
    <h1>{initializing ? "Getting the test browsers ready…" : elapsed < 3 ? "Checking in with the test browsers…" : "Waking up the test browsers…"}</h1>
    {!initializing && elapsed >= 3 && <p>Free hosting can take 30–60 seconds to wake up.</p>}
    <p className="timer">{elapsed} seconds elapsed</p>
    <p className="muted">This page opens on its own when everything is ready.</p>
  </section>{brief}</div>;
}
