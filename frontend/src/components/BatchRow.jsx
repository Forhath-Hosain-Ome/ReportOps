import { mono, body, STATUS_COLOR } from "../constants"
import { Label, SectionTitle } from "../primitives/Labels";
import { Btn, Section, IconBtn2, PrimaryBtn, IconBtn } from "../primitives/index";
import DownloadDropdown from "./DownloadDropdown";

export default function AuditBatchRow({ batch, action, onAction }) {
  const color    = STATUS_COLOR[batch.status] || "var(--color-muted)";
  const total     = batch.total_files     ?? 0;
  const processed = batch.processed_files ?? 0;
  const failed    = batch.failed_files    ?? 0;
  const pairLabel = batch.pair
    ? `${batch.pair.buyer?.name ?? ""} × ${batch.pair.factory?.name ?? ""}`
    : batch.pair_display ?? `Pair #${batch.pair_id}`;
  const date = batch.inspection_date ?? "—";
  const hasErrors = batch.status === "PARTIAL" || batch.status === "FAILED";

  // When this list is rendered in "retry-download" context (from the sidebar),
  // row click downloads the error JSON directly instead of navigating to detail.
  const isRetryContext = action === "retry-download";
  const handleRowClick = () =>
    isRetryContext ? onAction("retry-download", batch.id) : onAction("view", batch.id);

  return (
    <div
      onClick={handleRowClick}
      style={{
        display: "grid", gridTemplateColumns: "52px 1fr 90px 100px 90px 80px 96px",
        gap: "8px", padding: "10px 14px",
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`, borderRadius: "7px",
        alignItems: "center", cursor: "pointer", transition: "border-color 0.15s",
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = "var(--color-accent)"}
      onMouseLeave={e => e.currentTarget.style.borderLeft = `3px solid ${color}`}
    >
      <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)" }}>#{batch.id}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ ...body, fontSize: "12px", color: "var(--color-text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {pairLabel}
        </div>
        {batch.created_by && (
          <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>by {batch.created_by.username}</div>
        )}
      </div>
      <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{date}</span>
      <span style={{ ...mono, fontSize: "9px", color, background: `${color}18`, padding: "2px 7px", borderRadius: "3px", whiteSpace: "nowrap", display: "inline-block" }}>
        {batch.status}
      </span>
      <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
        {processed}/{total}
        {failed > 0 && <span style={{ color: "var(--color-error)", marginLeft: "4px" }}>({failed}✕)</span>}
      </span>
      <span style={{ ...mono, fontSize: "11px", color: batch.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)" }}>
        {batch.success_rate ?? "—"}%
      </span>
      <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }} onClick={e => e.stopPropagation()}>
        {isRetryContext ? (
          /* In retry-download context: only show the download button */
          <IconBtn
            title={hasErrors ? "Download error JSON" : "No blocked records"}
            color={hasErrors ? "var(--color-warning)" : undefined}
            disabled={!hasErrors}
            onClick={() => onAction("retry-download", batch.id)}
          >⬇</IconBtn>
        ) : (
          <>
            <IconBtn title="View detail" onClick={() => onAction("view", batch.id)}>◎</IconBtn>
            <IconBtn title="Batch logs" onClick={() => onAction("logs", batch.id)}>∷</IconBtn>
            {hasErrors && (
              <IconBtn
                title="Download error JSON"
                color="var(--color-warning)"
                onClick={() => onAction("retry-download", batch.id)}
              >⬇</IconBtn>
            )}
          </>
        )}
      </div>
    </div>
  );
}


export function BatchRow({ batch, onAction }) {
  const color    = STATUS_COLOR[batch.status] || "var(--color-muted)";
  const canRetry = batch.status === "PARTIAL" || batch.status === "FAILED";
  const hasExcel = !!batch.excel_report_path || batch.excel_available;
  const reports  = batch.reports || [];
  // Support both puma (total_pdfs) and image (total_folders) batch types
  const total     = batch.total_folders ?? batch.total_pdfs ?? 0;
  const processed = batch.processed_folders ?? batch.processed_pdfs ?? 0;
  
  return (
    <div className="items-center gap-2 px-3.5 py-2.5 cursor-pointer border rounded-[7px] transition-colors duration-150 batch-row"
      onClick={() => onAction("view", batch.id)}
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <span className="text-[11px]"
      style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent2)" }}>
        {batch.created_at}
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {batch.factory_code || "—"}
        </div>
        {batch.created_by && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {batch.created_by.username}
          </div>
        )}
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color, background: `${color}18`, padding: "2px 7px", borderRadius: "3px", whiteSpace: "nowrap", display: "inline-block" }}>
        {batch.status}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)" }}>
        {processed}/{total}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: batch.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)" }}>
        {batch.success_rate}%
      </span>
      <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
        <IconBtn2 title={canRetry ? "Retry failed" : "No failures to retry"} disabled={!canRetry} color="var(--color-warning)" onClick={() => onAction("retry", batch.id)}>
          ↺
        </IconBtn2>
        <IconBtn2 title="View logs" onClick={() => onAction("logs", batch.id)}>∷</IconBtn2>
        <DownloadDropdown
          batchId={batch.id}
          hasExcel={hasExcel}
          reports={reports}
          reportCount={batch.report_count || reports.length || 0}
          onAction={(key) => onAction(key, batch.id, { reports, hasExcel })}
        />
      </div>
    </div>
  );
}