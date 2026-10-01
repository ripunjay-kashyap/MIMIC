export function Bar({ label, value, threshold, risk = false }: { label: string; value: number; threshold?: number; risk?: boolean }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  const level = risk ? value >= .6 ? "risk-high" : value >= .3 ? "risk-mid" : "risk-low" : "";
  return <div className="bar-field"><div className="bar-label"><span>{label}</span><span>{percent}%</span></div>
    <div className="bar-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
      <div className={`bar-fill ${level}`} style={{ width: `${percent}%` }} />
      {threshold !== undefined && <span className="bar-marker" style={{ left: `${threshold * 100}%` }} title={`Abandons at ${Math.round(threshold * 100)}%`} />}
    </div>
  </div>;
}
