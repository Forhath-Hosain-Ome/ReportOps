
function BatchLogsView({ data }) {
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: 0 }}>
          Batch #{data?.batch_id} · Logs
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-warning)", background: "rgba(245,158,11,0.1)", padding: "2px 8px", borderRadius: "3px" }}>
          {data?.total_failed} failed · {data?.unretried} unretried
        </span>
      </div>
      {(data?.failed_pdfs || data?.failed_folders || []).map((f) => (
        <div key={f.id} style={{ padding: "10px 14px", background: "var(--color-surface)", borderRadius: "6px", borderLeft: `2px solid ${f.retried ? "var(--color-success)" : "var(--color-error)"}` }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: f.retried ? "var(--color-success)" : "var(--color-error)" }}>
            {f.filename || f.folder_name}
          </div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", marginTop: "4px" }}>{f.reason}</div>
        </div>
      ))}
      {data?.error_log && (
        <Section title="Raw Error Log">
          <pre style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Section>
      )}
    </div>
  );
}

export default BatchLogsView;