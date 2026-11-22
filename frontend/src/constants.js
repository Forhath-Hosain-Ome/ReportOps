export const mono  = { fontFamily: "var(--font-mono)" };
export const body  = { fontFamily: "var(--font-body)" };
export const disp  = { fontFamily: "var(--font-display)" };

export const fieldStyle = {
  width: "100%", padding: "9px 12px",
  background: "var(--color-panel)", border: "1px solid var(--color-border)",
  borderRadius: "6px", color: "var(--color-text)",
  fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none",
  boxSizing: "border-box",
};

export const STATUS_COLOR = {
  COMPLETED:  "var(--color-success)",
  PARTIAL:    "var(--color-warning)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export const pickBtnStyle = {
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.25)",
  color: "var(--color-accent2)",
  padding: "8px 16px",
  borderRadius: "6px",
  fontFamily: "var(--font-mono)",
  fontSize: "11px",
  cursor: "pointer",
  transition: "all 0.15s",
};

export const inputStyle = {
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-panel)",
  color: "var(--color-text)",
  fontFamily: "var(--font-mono)",
  fontSize: "12px",
  width: "180px",
};

export const ghostBtn = {
  background: "transparent", border: "1px solid var(--color-border)",
  color: "var(--color-muted)", padding: "6px 16px", borderRadius: "5px",
  fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
};