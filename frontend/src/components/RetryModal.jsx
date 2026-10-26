import { useState } from "react";


function RetryModal({ failedPdfs, onConfirm, onCancel, identityField }) {
  const [selected, setSelected] = useState(
    failedPdfs.filter((f) => !f.retried).map((f) => identityField ? f[identityField] : (f.filename || f.folder_name))
  );
  const toggle = (name) =>
    setSelected((prev) => prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]);
  const allUnretried = failedPdfs.filter((f) => !f.retried);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
      <div className="fade-up" style={{
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderRadius: "12px", padding: "24px 28px", minWidth: "400px", maxWidth: "560px",
        display: "flex", flexDirection: "column", gap: "16px",
      }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: "15px", fontWeight: 700, color: "var(--color-text)" }}>
          Retry Failed Items
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", maxHeight: "300px", overflowY: "auto" }}>
          {failedPdfs.map((f) => {
            const name = identityField ? f[identityField] : (f.filename || f.folder_name);
            return (
              <label key={name} style={{
                display: "flex", alignItems: "flex-start", gap: "10px",
                padding: "8px 12px", borderRadius: "6px",
                background: f.retried ? "rgba(34,211,160,0.05)" : "rgba(244,63,94,0.05)",
                border: `1px solid ${f.retried ? "rgba(34,211,160,0.15)" : "rgba(244,63,94,0.15)"}`,
                cursor: f.retried ? "default" : "pointer", opacity: f.retried ? 0.5 : 1,
              }}>
                <input type="checkbox" disabled={f.retried} checked={selected.includes(name)} onChange={() => toggle(name)} style={{ marginTop: "2px", accentColor: "var(--color-accent)" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", wordBreak: "break-all" }}>
                    {f.filename || f.folder_name}{f.retried && <span style={{ color: "var(--color-success)", marginLeft: "8px" }}>✓ already retried</span>}
                  </div>
                  {f.reason && <div style={{ fontFamily: "var(--font-body)", fontSize: "10px", color: "var(--color-muted)", marginTop: "2px" }}>{f.reason}</div>}
                </div>
              </label>
            );
          })}
        </div>
        <div className="flex flex-between flex-center gap-2" >
          <span className="desc font-[10px]" >
            {selected.length} of {allUnretried.length} selected
          </span>
          <div className="flex gap-2" >
            <button className="ghostBtn" onClick={onCancel}>Cancel</button>
            <button disabled={!selected.length} onClick={() => onConfirm(selected)} className="ghostBtn" style={{ background: selected.length ? "var(--color-accent)" : "var(--color-border)", color: selected.length ? "#fff" : "var(--color-muted)", borderColor: selected.length ? "var(--color-accent)" : "var(--color-border)", cursor: selected.length ? "pointer" : "not-allowed" }}>
              Retry {selected.length ? `(${selected.length})` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RetryModal;