export function Section({ title, children }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.08em", color: "var(--color-muted)", marginBottom: "8px" }}>{title.toUpperCase()}</div>
      {children}
    </div>
  );
}