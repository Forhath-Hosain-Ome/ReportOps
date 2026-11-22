import { disp, body, mono } from "../constants"

function SettingsView({ data, settingsKey }) {
  const records = Array.isArray(data) ? data : (data?.results ?? []);
  const titles  = { buyers: "Buyers", factories: "Factories", pairs: "Buyer–Factory Pairs" };

  const renderRecord = (r) => {
    if (settingsKey === "buyers") {
      return (
        <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px", gap: "10px", alignItems: "center" }}>
          <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.name}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.code}</span>
          <span style={{ ...mono, fontSize: "9px", color: r.is_active ? "var(--color-success)" : "var(--color-error)", background: r.is_active ? "rgba(34,211,160,0.1)" : "rgba(244,63,94,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
            {r.is_active ? "ACTIVE" : "INACTIVE"}
          </span>
        </div>
      );
    }
    if (settingsKey === "factories") {
      return (
        <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 80px 80px", gap: "10px", alignItems: "center" }}>
          <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.name}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.buyer_name ?? `Buyer #${r.buyer}`}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.code}</span>
          <span style={{ ...mono, fontSize: "9px", color: r.is_active ? "var(--color-success)" : "var(--color-error)", background: r.is_active ? "rgba(34,211,160,0.1)" : "rgba(244,63,94,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
            {r.is_active ? "ACTIVE" : "INACTIVE"}
          </span>
        </div>
      );
    }
    // pairs
    return (
      <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 100px auto", gap: "10px", alignItems: "center" }}>
        <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.buyer_name ?? `Buyer #${r.buyer}`}</span>
        <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.factory_name ?? `Factory #${r.factory}`}</span>
        <span style={{ ...mono, fontSize: "10px", color: "var(--color-accent2)", background: "rgba(99,102,241,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
          {r.report_type}
        </span>
        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          {(r.available_reports ?? []).map(ar => (
            <span key={ar} style={{ ...mono, fontSize: "9px", color: "var(--color-muted)", background: "var(--color-panel)", border: "1px solid var(--color-border)", padding: "1px 5px", borderRadius: "3px" }}>
              {ar}
            </span>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
          {titles[settingsKey]}
        </h2>
        <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
          ({records.length} record{records.length !== 1 ? "s" : ""})
        </span>
      </div>
      <div style={{ ...mono, fontSize: "11px", color: "var(--color-muted)", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: "7px", padding: "10px 14px" }}>
        ⚙ Registration is managed via the Django admin or API. This view is read-only.
        To add or edit records go to <strong>/admin/</strong>.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {records.map((r, i) => (
          <div key={r.id ?? i} style={{
            padding: "10px 14px", background: "var(--color-surface)",
            border: "1px solid var(--color-border)", borderRadius: "6px",
          }}>
            {renderRecord(r)}
          </div>
        ))}
        {records.length === 0 && (
          <div style={{ ...body, fontSize: "13px", color: "var(--color-muted)", padding: "24px 0", textAlign: "center" }}>
            No records found.
          </div>
        )}
      </div>
    </div>
  );
}

export default SettingsView;