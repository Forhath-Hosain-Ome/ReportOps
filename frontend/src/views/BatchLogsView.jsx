import { disp, mono, STATUS_COLOR } from "../constants"
import { Label, SectionTitle, PrimaryBtn } from "../primitives/index";

function AuditBatchLogsView({ data }) {
  const color = STATUS_COLOR[data?.status] || "var(--color-muted)";
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
      <h2 style={{ ...disp, fontSize: "16px", fontWeight: 700, margin: 0 }}>
        Batch #{data?.id} · Logs
      </h2>
      <StatGrid stats={[
        ["Status",    data?.status,         color],
        ["Total",     data?.total_files],
        ["Processed", data?.processed_files],
        ["Failed",    data?.failed_files,   data?.failed_files > 0 ? "var(--color-error)" : undefined],
      ]} />
      {data?.error_log ? (
        <Card accent="var(--color-error)">
          <SectionTitle>RAW ERROR LOG</SectionTitle>
          <pre style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Card>
      ) : (
        <div style={{ ...mono, fontSize: "11px", color: "var(--color-success)", padding: "8px 0" }}>
          ✓ No errors — all files processed successfully
        </div>
      )}
    </div>
  );
}

export default AuditBatchLogsView;