import { useOutputStore } from "../../store/outputStore";
import {
  downloadCertificate as downloadCertificatePuma,
  downloadReportPDF as downloadReportPDFPuma,
  fetchReport as fetchReportPuma,
  fetchCertificateLogs,
} from "../../services/pumaApi";
import {
  fetchReport as fetchReportImage,
  downloadReportPDF as downloadReportPDFImage,
  downloadReportDOCX as downloadReportDOCXImage,
} from "../../services/defectImageApi";
import {
  fetchBatchDetail,
  downloadErrorJson,
} from "../../services/finalSummaryApi";

function saveBlob(blob, filename) {
  filename = blob?.filename || filename;
  blob = blob?.blob || blob;
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/**
 * Download PDF and DOCX certificate for a report.
 *
 * BUG FIX — only DOCX was downloading:
 * Browsers silently drop programmatic anchor clicks that happen within the
 * same synchronous tick (or too close together). The original code called
 * saveBlob twice back-to-back after Promise.allSettled resolved — the browser
 * swallowed the first click and only executed the second. Fix: stagger the
 * two saveBlob calls with a small setTimeout so each lives in its own task.
 */
async function downloadBoth(report, downloadReportPDFFn, downloadCertificateFn, addLog) {
  addLog({ level: "info", message: `Downloading PDF + Certificate for ${report.style}…` });

  const pdfFilename = (
    `Apparel Report_${report.style} ${report.factory_code || ""}, ` +
    `Puma Warehouse WH AQL, PO ${report.po_numbers?.[0]?.number || ""}, ` +
    `Customer ${report.final_customer || ""}.pdf`
  );
  const docxFilename = (
    `${report.report_date || ""} ` +
    `${report.style || report.folder_name || "report"}(${report.po_numbers?.map((p) => p.number).join(",") || ""}) ` +
    `${report.factory_name || ""}.docx`
  );

  const [pdfResult, certResult] = await Promise.allSettled([
    downloadReportPDFFn(report.id),
    downloadCertificateFn(report.id),
  ]);

  // Trigger PDF download first …
  if (pdfResult.status === "fulfilled") {
    saveBlob(pdfResult.value, pdfFilename);
    addLog({ level: "success", message: `PDF downloaded: ${pdfFilename}` });
  } else {
    addLog({ level: "error", message: `PDF failed: ${pdfResult.reason?.response?.data?.detail || pdfResult.reason?.message}` });
  }

  // … then DOCX 300 ms later so the browser treats them as separate user-gesture tasks.
  await new Promise((res) => setTimeout(res, 300));

  if (certResult.status === "fulfilled") {
    saveBlob(certResult.value, docxFilename);
    addLog({ level: "success", message: `Certificate downloaded: ${docxFilename}` });
  } else {
    addLog({ level: "error", message: `Certificate failed: ${certResult.reason?.response?.data?.detail || certResult.reason?.message}` });
  }
}

// ── Report list ───────────────────────────────────────────────────────────────
// FIX — row click behaviour:
// Previously the row called onSelect(id, action), which meant clicking a row
// in "Download Cert + PDF" mode triggered the download directly without ever
// showing the report detail. Now every row click ALWAYS navigates to the report
// detail (action = "view"). The action passed from the sidebar is forwarded to
// the detail page so it can show the right contextual button / auto-trigger there.
function ReportList({ data, onSelect, action = "view" }) {
  const results = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);

  // Heuristic to detect if we are listing Audit batches instead of reports
  const isBatchList = results.length > 0 && (results[0].total_files !== undefined);

  const sorted  = [...results].sort((a, b) => {
    const dateA = a.report_date || a.inspection_date || a.created_at || "";
    const dateB = b.report_date || b.inspection_date || b.created_at || "";
    if (dateA !== dateB) return dateB.localeCompare(dateA);
    return b.id - a.id;
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: "0 0 8px" }}>
        Reports <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({sorted.length})</span>
      </h2>
      {sorted.map((r) => (
        <div
          key={r.id}
          // Respect the contextual action passed from the sidebar (view, logs, retry-download)
          onClick={() => onSelect(r.id, action)}
          style={{
            display: "flex", gap: "12px", padding: "10px 14px",
            background: "var(--color-surface)", borderRadius: "6px",
            border: "1px solid var(--color-border)",
            cursor: "pointer", transition: "border-color 0.15s", alignItems: "center",
          }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = "var(--color-accent)"}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--color-border)"}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)", minWidth: "80px" }}>
            {r.style || (isBatchList ? `BATCH #${r.id}` : "N/A")}
          </span>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)", flex: 1 }}>
            {r.folder_name ? r.status : (r.factory_name || r.factory_code || (isBatchList ? `Status: ${r.status}` : "Unknown"))}
          </span>
          {(r.report_number || (isBatchList && r.processed_files != null)) && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent)", background: "rgba(99,102,241,0.1)", padding: "1px 7px", borderRadius: "3px" }}>
              {r.report_number ? `#${r.report_number}` : `Files: ${r.processed_files}/${r.total_files}`}
            </span>
          )}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            {r.inspection_date || (r.created_at ? new Date(r.created_at).toLocaleDateString() : "")}
          </span>
          {r.po_numbers && (
            <span style={{ fontFamily: "var(--font-body)", fontSize: "10px", color: "var(--color-muted)" }}>
              {r.po_numbers?.map((p) => p.number).join(", ")}
            </span>
          )}
          {isBatchList && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
              Format: {r.format_type || "N/A"}
            </span>
          )}
          <span style={{ color: "var(--color-muted)", fontSize: "12px" }}>→</span>
        </div>
      ))}
    </div>
  );
}

// ── Report detail ─────────────────────────────────────────────────────────────
function ReportDetail({ data, downloadReportPDFFn, downloadCertificateFn }) {
  const { addLog } = useOutputStore();

  const fields = [
    ["Report Number",   data?.report_number || "—"],
    ["Report Date",     data?.report_date],
    ["Style",           data?.style],
    ["Description",     data?.description],
    ["Factory Code",    data?.factory_code],
    ["Factory Name",    data?.factory_name],
    ["Final Customer",  data?.final_customer],
    ["Inspection Date", data?.inspection_date],
    ["Sample Size",     data?.sample_size],
    ["PO Qty",          data?.po_qty],
    ["Actual Qty",      data?.actual_qty],
    ["Inspected Qty",   data?.inspected_qty],
    ["Major Defect",    data?.major_defect],
    ["Minor Defect",    data?.minor_defect],
    ["Batch Status",    data?.status],
    ["Total Files",     data?.total_files],
    ["Processed",       data?.processed_files],
    ["Failed",          data?.failed_files],
    ["Format Type",     data?.format_type],
    ["Submitted images", data?.submitted_images], ["Successful images", data?.successful_images], ["Failed images", data?.failed_images],
  ];

  // Heuristic to check if we are viewing a Batch Detail instead of a Report
  const isBatch = data?.status !== undefined && data?.total_files !== undefined;
  const title = isBatch ? `Batch #${data.id}` : (data?.style || `Report #${data.id}`);

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          {title}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          #{data?.id}
        </span>
        {data?.report_number && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent)", background: "rgba(99,102,241,0.1)", padding: "2px 10px", borderRadius: "4px" }}>
            Report #{data.report_number}
          </span>
        )}
        {data?.created_by && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {!isBatch && (!data.folder_name || data.current_attempt_id) && downloadReportPDFFn && downloadCertificateFn && (
          <button
            onClick={() => downloadBoth(data, downloadReportPDFFn, downloadCertificateFn, addLog)}
            style={{
              background: "rgba(34,211,160,0.1)", border: "1px solid rgba(34,211,160,0.25)",
              color: "var(--color-success)", padding: "5px 16px", borderRadius: "5px",
              fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
              display: "flex", alignItems: "center", gap: "6px",
            }}
          >
            {data.folder_name ? "⬇ PDF + DOCX" : "⬇ PDF + Certificate"}
          </button>
        )}
      </div>

      {/* Fields grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" }}>
        {fields.map(([label, val]) => val != null && val !== "" && (
          <div
            key={label}
            style={{
              background: "var(--color-surface)", border: "1px solid var(--color-border)",
              borderRadius: "6px", padding: "10px 14px",
              borderLeft: (label === "Report Date" || label === "Inspection Date")
                ? "2px solid var(--color-accent2)"
                : "1px solid var(--color-border)",
            }}
          >
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
              {label.toUpperCase()}
            </div>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)" }}>
              {String(val)}
            </div>
          </div>
        ))}
      </div>

      {data?.attempts?.length > 0 && <section><h3>Processing and retry history</h3>{data.attempts.map((attempt) => <article key={attempt.id}>
        <strong>Generation {attempt.generation}: {attempt.status}</strong><p>{attempt.stage} {attempt.error_code} {attempt.reason}</p>
        {attempt.outcomes.map((image) => <p key={image.id}>{image.original_filename}: {image.status} {image.failure_reason}</p>)}
      </article>)}</section>}
      {/* PO Numbers */}
      {data?.po_numbers?.length > 0 && (
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "8px" }}>
            PO NUMBERS
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {data.po_numbers.map((p) => (
              <span key={p.id} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)", background: "rgba(99,102,241,0.1)", padding: "3px 10px", borderRadius: "4px" }}>
                {p.number}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Certificate history */}
      {data?.certificate_logs?.length > 0 && (
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "8px" }}>
            CERTIFICATE HISTORY
          </div>
          {data.certificate_logs.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: "10px", padding: "7px 12px", background: "var(--color-surface)", borderRadius: "5px", border: "1px solid var(--color-border)", marginBottom: "4px", fontSize: "11px" }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-muted)" }}>
                {new Date(c.generated_at).toLocaleString()}
              </span>
              <span style={{ color: "var(--color-muted)" }}>by {c.generated_by || "system"}</span>
              {c.was_downloaded
                ? <span style={{ color: "var(--color-success)", marginLeft: "auto" }}>✓ downloaded</span>
                : <span style={{ color: "var(--color-warning)", marginLeft: "auto" }}>not downloaded</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────
export default function ReportOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();
  const isImage = output?.source === "image";
  const isAudit = output?.source === "audit";

  const fetchReportFn = isAudit ? fetchBatchDetail : (isImage ? fetchReportImage : fetchReportPuma);
  const downloadReportPDFFn = isImage ? downloadReportPDFImage : downloadReportPDFPuma;
  const downloadCertificateFn = isImage ? downloadReportDOCXImage : downloadCertificatePuma;

  // Row clicks always land here with action = "view" now.
  // The "certificate" case in the sidebar still works: PumaPage sets
  // action: "certificate" on the list, but row clicks override to "view"
  // so the user sees the detail page and clicks the download button themselves.
  const handleSelect = async (id, action = "view") => {
    switch (action) {
      case "view":
        setLoading(true);
        try {
          const data = await fetchReportFn(id);
          setOutput("report", data, `Report · ${data.style || data.folder_name || id}`, { source: output.source });
          addLog({ level: "info", message: `Loaded report ${data.style || data.folder_name || id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load report #${id}` });
          setLoading(false);
        }
        break;

      case "retry-download":
        setLoading(true);
        try {
          addLog({ level: "info", message: `Downloading error JSON for batch #${id}...` });
          const blob = await downloadErrorJson(id);
          const filename = `error_batch_${id}_${new Date().toISOString().split('T')[0]}.json`;
          saveBlob(blob, filename);
          addLog({ level: "success", message: `Downloaded: ${filename}` });
          setLoading(false);
        } catch (e) {
          addLog({ level: "error", message: `Download failed: ${e.message}` });
          setLoading(false);
        }
        break;

      case "certificate":
        // Reached only if something explicitly calls onSelect with "certificate"
        // (not from a row click anymore). Fetch the full report then download both.
        addLog({ level: "info", message: `Loading Report #${id}…` });
        try {
          const data = await fetchReportFn(id);
          await downloadBoth(data, downloadReportPDFFn, downloadCertificateFn, addLog);
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
        }
        break;

      case "cert-logs":
        setLoading(true);
        try {
          const data = await fetchCertificateLogs(id);
          setOutput(
            "report",
            { certificate_logs: data.results || data, id, style: `Report #${id}` },
            `Cert Logs · #${id}`
          );
          addLog({ level: "info", message: `${(data.results || data).length} certificate events` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load cert logs for Report #${id}` });
          setLoading(false);
        }
        break;
    }
  };

  if (output.type === "report-list") return <ReportList data={output.data} onSelect={handleSelect} action={output.action} />;
  if (output.type === "report")      return (
    <ReportDetail 
      data={output.data} 
      downloadReportPDFFn={downloadReportPDFFn} 
      downloadCertificateFn={downloadCertificateFn} 
    />
  );
  return null;
}
