export function Stat({ label, value }) {
  return (
    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "7px", padding: "12px 14px" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "6px" }}>{label.toUpperCase()}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, color: "var(--color-text)" }}>{value ?? "—"}</div>
    </div>
  );
}