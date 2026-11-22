import { disp, mono, STATUS_COLOR } from "../constants"
import { Label, SectionTitle, PrimaryBtn, StatGrid } from "../primitives/index";

function AuditBatchDetail({ data }) {
  const color     = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const total     = data?.total_files     ?? 0;
  const processed = data?.processed_files ?? 0;
  const failed    = data?.failed_files    ?? 0;
  const pairLabel = data?.pair
    ? `${data.pair.buyer?.name ?? ""} × ${data.pair.factory?.name ?? ""}`
    : `Pair #${data?.pair_id}`;

  const reports = data?.reports ?? [];

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: 0 }}>Batch #{data?.id}</h2>
        <span style={{ ...mono, fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        {data?.created_by && (
          <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
      </div>

      {/* Meta */}
      <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
        {[
          ["Pair",    pairLabel],
          ["Date",    data?.inspection_date ?? "—"],
          ["Format",  data?.format_type ?? data?.pair?.report_type ?? "—"],
        ].map(([k, v]) => (
          <div key={k} style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
            <span style={{ opacity: 0.6 }}>{k}: </span>
            <span style={{ color: "var(--color-text)" }}>{v}</span>
          </div>
        ))}
      </div>

      <StatGrid stats={[
        ["Total",     total],
        ["Processed", processed],
        ["Failed",    failed,  failed > 0 ? "var(--color-error)" : undefined],
        ["Success",   `${data?.success_rate ?? 0}%`, data?.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)"],
      ]} />

      {/* Error log */}
      {data?.error_log && (
        <Card accent="var(--color-error)">
          <SectionTitle>ERROR LOG</SectionTitle>
          <pre style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Card>
      )}

      {/* Reports nested */}
      {reports.length > 0 && (
        <div>
          <SectionTitle>REPORTS ({reports.length})</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {reports.map(r => (
              <div key={r.id} style={{
                display: "grid", gridTemplateColumns: "1fr 120px 120px 120px 80px",
                gap: "10px", padding: "9px 14px",
                background: "var(--color-surface)", border: "1px solid var(--color-border)",
                borderRadius: "5px", alignItems: "center",
              }}>
                <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.factory || r.file_name}
                </span>
                <span className="batch-font">{r.style_no}</span>
                <span className="batch-font">{r.inspection_type}</span>
                <span className="batch-font">{r.date_of_issue}</span>
                <span style={{
                  ...mono, fontSize: "9px",
                  color: r.audit_result === "PASS" ? "var(--color-success)" : r.audit_result === "FAIL" ? "var(--color-error)" : "var(--color-muted)",
                }}>
                  {r.audit_result}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default AuditBatchDetail;