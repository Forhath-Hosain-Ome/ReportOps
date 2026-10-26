import { useState } from "react";
import { useOutputStore } from "../store/outputStore";
import {
  fetchBatch as fetchBatchPuma,
  retryBatch as retryBatchPuma,
  downloadExcel as downloadExcelPuma,
} from "../services/pumaApi";

import { saveBlob } from "../utils/fileUtils";
import { Btn, Section, Stat, StatGrid } from "../primitives/index";
import UploadForm from "./UploadForm";
import BatchList from "./BatchList";
import { STATUS_COLOR } from "../constants"
import RetryModal from "./RetryModal";
import { fetchBatch as fetchBatchImage, retryBatch as retryBatchImage, fetchBatchLogs } from "../services/defectImageApi";
import ReportCertBtn from "./ReportCertBtn";



export default function BatchDetail({ data, source = "puma" }) {
  const { addLog, setOutput } = useOutputStore();
  const [showRetryModal, setShowRetryModal] = useState(false);
  const isImage = source === "image";

  const color         = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const failedRecords = data?.failed_folder_records || data?.failed_pdf_records || [];
  const failedCount   = data?.failed_folders_count ?? data?.failed_pdfs_count ?? failedRecords.length;
  const retryReports = isImage ? (data?.reports || []).filter((r) => ["FAILED", "PARTIAL"].includes(r.status)) : failedRecords;
  const hasRetryable = isImage ? retryReports.length > 0 : failedRecords.some((f) => !f.retried);
  const recoverDispatch = isImage && (["FAILED", "UNKNOWN"].includes(data?.dispatch_state) || (data?.status === "PROCESSING" && data?.lease_expires_at && new Date(data.lease_expires_at) <= new Date()));
  const canRetry      = (data?.status === "PARTIAL" || data?.status === "FAILED") && hasRetryable;

  const total     = data?.total_folders ?? data?.total_pdfs ?? 0;
  const processed = data?.processed_folders ?? data?.processed_pdfs ?? 0;

  const handleRetryConfirm = async (names) => {
    setShowRetryModal(false);
    if (isImage) {
      try {
        await retryBatchImage(data.id, names);
        setOutput("batch", await fetchBatchImage(data.id), `Batch #${data.id}`, { source: "image" });
      } catch (e) { addLog({ level: "error", message: e.response?.data?.detail || e.message }); }
      return;
    }
    addLog({ level: "info", message: `Retrying ${names.length} item(s) in Batch #${data.id}…` });
    try {
      const res = await retryBatchPuma(data.id, names);
      addLog({ level: "success", message: `Retry started — ${res.files_retrying?.length} file(s)` });
      const updated = await fetchBatchPuma(data.id);
      setOutput("batch", updated, `Batch #${data.id}`);
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const handleExcel = async () => {
    if (isImage) { addLog({ level: "warning", message: "Excel download unavailable for image batches." }); return; }
    try {
      const blob = await downloadExcelPuma(data.id);
      saveBlob(blob, `batch-${data.id}.xlsx`);
      addLog({ level: "success", message: `Excel downloaded for Batch #${data.id}` });
    } catch (e) {
      addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {showRetryModal && (
        <RetryModal failedPdfs={retryReports} identityField={isImage ? "id" : undefined} onConfirm={handleRetryConfirm} onCancel={() => setShowRetryModal(false)} />
      )}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          Batch #{data?.id}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        {data?.created_by && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {isImage && <Btn onClick={async () => { try { setOutput("logs", await fetchBatchLogs(data.id), `Logs · Batch #${data.id}`, { source: "image", batchId: data.id }); } catch (e) { addLog({ level: "error", message: e.message }); } }}>Logs and retry history</Btn>}
        {data?.excel_available && <Btn onClick={handleExcel} accent>⬇ Excel</Btn>}
        {recoverDispatch && <Btn onClick={() => handleRetryConfirm()}>Recover dispatch</Btn>}
        {canRetry && <Btn onClick={() => setShowRetryModal(true)}>↺ Retry Failed</Btn>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
        {[
          ["Total",       total],
          ["Processed",   processed],
          ["Failed",      failedCount],
          ...(isImage ? [["Partial", data.partial_reports], ["Submitted images", data.submitted_images], ["Successful images", data.successful_images], ["Failed images", data.failed_images]] : []),
          ["Success",     `${data?.success_rate}%`],
        ].map(([label, val]) => <Stat key={label} label={label} value={val} />)}
      </div>

      {isImage && <p role="status">{data.dispatch_state} {data.last_error_code} {data.error_log}</p>}
      {failedRecords.length > 0 && (
        <Section title="Failed Items">
          {failedRecords.map((f) => (
            <div key={f.id} style={{ padding: "8px 12px", background: "rgba(244,63,94,0.06)", borderRadius: "5px", borderLeft: "2px solid var(--color-error)", marginBottom: "4px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-error)" }}>
                {f.filename || f.folder_name}
              </div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", marginTop: "2px" }}>{f.reason}</div>
              {f.retried && <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-success)" }}>✓ retried</span>}
            </div>
          ))}
        </Section>
      )}

      {data?.reports?.length > 0 && (
        <Section title={`Reports (${data.reports.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {data.reports.map((r) => (
              <div key={r.id} style={{ display: "flex", gap: "12px", padding: "8px 12px", background: "var(--color-panel)", borderRadius: "5px", border: "1px solid var(--color-border)", fontSize: "12px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent2)", minWidth: "80px" }}>
                  {r.folder_name || r.style}
                </span>
                <span style={{ color: "var(--color-muted)" }}>{r.factory_code || r.status}</span>
                <span style={{ color: "var(--color-muted)", fontSize: "10px", flex: 1 }}>
                  {r.image_count ? `${r.image_count} images` : (r.po_numbers?.map((p) => p.number).join(", "))}
                </span>
                {(!isImage || r.current_attempt_id) && <ReportCertBtn reportId={r.id} styleName={r.folder_name || r.style} pdfFilename={r.pdf_filename} source={source} />}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
