export function StatGrid({ stats }) {
  return (
    <div className="stat-grid" style={{ display: "grid", gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: "8px" }}>
      {stats.map(([label, val, color]) => (
        <div key={label} className="stat-card">
          <div className="mono stat-label">{label}</div>
          <div className="disp stat-value" style={{ color: color || "var(--color-text)" }}>{val ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}