import { useState, useCallback, useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import { useOutputStore } from "../store/outputStore";
import {
  uploadBatch,
  fetchBatches,
  // fetchBatch,
  fetchBatchLogs,
  fetchErrorJson,
  retryBatch,
  downloadSummary,
  fetchFilterOptions,
} from "../services/finalSummaryApi";
import useAuditWs from "../hooks/useAuditWs";

// ── Shared styles ─────────────────────────────────────────────────────────────
const hdr = {
  fontFamily: "var(--font-display)", fontSize: "18px",
  fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)",
};
const sub = {
  fontFamily: "var(--font-body)", fontSize: "13px",
  color: "var(--color-muted)", margin: 0, lineHeight: 1.6,
};
const fieldStyle = {
  width: "100%", padding: "9px 12px",
  background: "var(--color-panel)", border: "1px solid var(--color-border)",
  borderRadius: "6px", color: "var(--color-text)",
  fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none",
  boxSizing: "border-box",
};


// ── Stage tab button ──────────────────────────────────────────────────────────
function StageTab({ label, active, onClick, badge }) {
  return (
    <button onClick={onClick} style={{
      position: "relative",
      background: active ? "var(--color-accent)" : "transparent",
      color: active ? "#fff" : "var(--color-muted)",
      border: "none", padding: "6px 18px", borderRadius: "5px",
      fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 500,
      letterSpacing: "0.08em", cursor: "pointer", transition: "all 0.15s",
    }}>
      {label}
      {badge > 0 && (
        <span style={{
          position: "absolute", top: "-4px", right: "-4px",
          background: "var(--color-error)", color: "#fff",
          borderRadius: "8px", fontSize: "8px", fontWeight: 700,
          padding: "1px 5px", lineHeight: 1.4,
        }}>
          {badge}
        </span>
      )}
    </button>
  );
}

// ── Label ─────────────────────────────────────────────────────────────────────
function Label({ children, required }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "10px",
      color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "5px",
    }}>
      {children}{required && <span style={{ color: "var(--color-error)", marginLeft: "2px" }}>*</span>}
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────
function ProgressBar({ progress }) {
  if (!progress) return null;
  return (
    <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "14px", border: "1px solid var(--color-border)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>
          {progress.stage}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          {progress.processed}/{progress.total}
        </span>
      </div>
      <div style={{ height: "4px", background: "var(--color-border)", borderRadius: "2px", overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${progress.percent}%`,
          background: progress.stage === "DONE" ? "var(--color-success)" : "var(--color-accent)",
          borderRadius: "2px", transition: "width 0.4s ease",
        }} />
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// STAGE 1 — Upload
// ════════════════════════════════════════════════════════════════════════════════
function UploadStage({ onComplete }) {
  const { addLog } = useOutputStore();
  const [files, setFiles]       = useState([]);
  const [isDragOver, setIsDrag] = useState(false);
  const [batchId, setBatchId]   = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy]         = useState(false);
  const [formatType, setFormatType] = useState("SPI");  // SPI, REGULAR, SWEATER
  const inputRef = useRef(null);

  const addFiles = useCallback((incoming) => {
    const valid = [...incoming].filter(f =>
      f.name.toLowerCase().endsWith(".xlsx") || f.name.toLowerCase().endsWith(".xls")
    );
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...valid.filter(f => !names.has(f.name))];
    });
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault(); setIsDrag(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles]);

  useAuditWs(batchId, {
    onProgress: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" });
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} records saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} file(s) failed — check Logs tab to fix` });
      setBusy(false);
      onComplete(msg.batch_id, msg.report_count, msg.failed || 0);
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch error: ${msg.error_message}` });
      setBusy(false); setProgress(null); setBatchId(null);
    },
  });

  const handleUpload = async () => {
    if (!files.length || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading ${files.length} Excel file(s)…` });
    try {
      const data = await uploadBatch(files, formatType);
      setBatchId(data.batch_id);
      setProgress({ processed: 0, total: data.total_files, percent: 0, stage: "QUEUED" });
      addLog({ level: "success", message: `Batch #${data.batch_id} created — ${data.total_files} file(s) queued` });
    } catch (e) {
      const msg = e.response?.data?.files?.[0] || e.response?.data?.detail || e.message;
      addLog({ level: "error", message: `Upload failed: ${msg}` });
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "640px" }}>
      <div>
        <h2 style={hdr}>Stage 1 — Upload Excel Files</h2>
        <p style={sub}>Upload one or many audit report Excel files (.xlsx / .xls). Data is extracted and saved to the database automatically.</p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDragOver ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "48px 24px", textAlign: "center", cursor: "pointer",
          background: isDragOver ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={inputRef} type="file" accept=".xlsx,.xls" multiple style={{ display: "none" }}
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
        <div style={{ fontSize: "32px", marginBottom: "12px" }}>📊</div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "14px", color: "var(--color-text)", marginBottom: "6px" }}>
          Drag & drop Excel files here, or click to browse
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          .xlsx and .xls · 50 MB per file max · Multiple files supported
        </div>
       </div>

       {/* Format selection */}
       <div style={{ display: "flex", gap: "18px", alignItems: "center", marginTop: "4px" }}>
         <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em" }}>
           FORMAT
         </span>
         <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
           <input
             type="radio"
             name="format"
             value="SPI"
             checked={formatType === "SPI"}
             onChange={() => setFormatType("SPI")}
           />
           <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)" }}>
             SPI Format (78)
           </span>
         </label>
         <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
           <input
             type="radio"
             name="format"
             value="REGULAR"
             checked={formatType === "REGULAR"}
             onChange={() => setFormatType("REGULAR")}
           />
           <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)" }}>
             Regular Format (35)
           </span>
         </label>
         <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
           <input
             type="radio"
             name="format"
             value="SWEATER"
             checked={formatType === "SWEATER"}
             onChange={() => setFormatType("SWEATER")}
           />
           <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)" }}>
             Sweater Format (37)
           </span>
         </label>
       </div>

       {/* File list */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
            {files.length} FILE(S) SELECTED
          </div>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "7px 12px", background: "var(--color-surface)",
              borderRadius: "5px", border: "1px solid var(--color-border)",
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
                📄 {f.name}
              </span>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                {!busy && (
                  <button onClick={(e) => { e.stopPropagation(); setFiles(prev => prev.filter((_, j) => j !== i)); }}
                    style={{ background: "none", border: "none", color: "var(--color-error)", cursor: "pointer", fontSize: "12px" }}>
                    ✕
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ProgressBar progress={progress} />

      <button onClick={handleUpload} disabled={!files.length || busy} style={{
        background: files.length && !busy ? "var(--color-accent)" : "var(--color-border)",
        color: files.length && !busy ? "#fff" : "var(--color-muted)",
        border: "none", padding: "11px 28px", borderRadius: "6px",
        fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
        letterSpacing: "0.06em", cursor: files.length && !busy ? "pointer" : "not-allowed",
        alignSelf: "flex-start", transition: "all 0.15s",
      }}>
        {busy ? "PROCESSING…" : "UPLOAD & EXTRACT"}
      </button>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// STAGE 2 — Export
// ════════════════════════════════════════════════════════════════════════════════
function ExportStage({ lastBatchId, lastCount }) {
  const { addLog } = useOutputStore();
  const [options, setOptions]  = useState(null);
  const [loading, setLoading]  = useState(false);
  const [exporting, setExport] = useState(false);
  const [form, setForm]        = useState({
    factory: "", client: "", date_from: "", date_to: "", style: "", po: "",
  });

  useEffect(() => {
    setLoading(true);
    fetchFilterOptions()
      .then(data => {
        setOptions({
          factories:  Array.isArray(data?.factories)  ? data.factories  : [],
          clients:    Array.isArray(data?.clients)    ? data.clients    : [],
          styles:     Array.isArray(data?.styles)     ? data.styles     : [],
          po_numbers: Array.isArray(data?.po_numbers) ? data.po_numbers : [],
          min_date:   data?.min_date ?? null,
          max_date:   data?.max_date ?? null,
        });
        setLoading(false);
      })
       .catch(e  => {
        addLog({ level: "error", message: `Options load failed: ${e.message}` });
        setOptions({ factories: [], clients: [], styles: [], po_numbers: [] });
        setLoading(false);
      });
  }, [lastBatchId, addLog]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const canExport = form.factory && form.client && form.date_from && form.date_to;

  const handleExport = async () => {
    if (!canExport || exporting) return;
    setExport(true);
    addLog({ level: "info", message: `Generating summary for ${form.factory} / ${form.client}…` });
    try {
      const params = {
        factory: form.factory, client: form.client,
        date_from: form.date_from, date_to: form.date_to,
        ...(form.style && { style: form.style }),
        ...(form.po    && { po: form.po }),
      };
      const { blob, headers } = await downloadSummary(params);
      const cd   = headers["content-disposition"] || "";
      const name = cd.match(/filename[^;=\n]*=['"]?([^'"\n]+)['"]?/)?.[1] || "audit_summary.xlsx";
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
      addLog({ level: "success", message: `Downloaded: ${name}` });
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      addLog({ level: "error", message: `Export failed: ${msg}` });
    } finally {
      setExport(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "640px" }}>
      <div>
        <h2 style={hdr}>Stage 2 — Download Summary</h2>
        <p style={sub}>Filter by factory, buyer, and date range to generate a grouped Excel summary with defect analysis charts.</p>
      </div>

      {lastBatchId && (
        <div style={{ background: "rgba(34,211,160,0.08)", border: "1px solid rgba(34,211,160,0.2)", borderRadius: "7px", padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-success)" }}>
          ✓ Batch #{lastBatchId} saved {lastCount} record(s) to the database. Filter below to export.
        </div>
      )}

      {loading && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-muted)", padding: "20px 0" }}>
          Loading filter options…
        </div>
      )}

      {!loading && options && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          
          {(options.factories || []).length === 0 && (options.clients || []).length === 0 && (
            <div style={{
              background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.3)",
              borderRadius: "7px", padding: "14px 18px",
              fontFamily: "var(--font-mono)", fontSize: "11px",
              color: "var(--color-warning)", lineHeight: 1.8,
            }}>
              ⚠ No data in the database yet.<br />
              <span style={{ opacity: 0.7 }}>
                Go to Stage 1 and upload Excel files first. You can still type factory and buyer names manually below.
              </span>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <Label required>FACTORY</Label>
              <input
                type="text"
                value={form.factory}
                placeholder="Type or select factory…"
                onChange={e => set("factory", e.target.value)}
                style={fieldStyle}
                list="fs-factory-opts"
              />
              <datalist id="fs-factory-opts">
                {Array.from(new Set(options?.factories || [])).map(f => <option key={f} value={f} />)}
              </datalist>
            </div>
            <div>
              <Label required>BUYER / CLIENT</Label>
              <input
                type="text"
                value={form.client}
                placeholder="Type or select buyer…"
                onChange={e => set("client", e.target.value)}
                style={fieldStyle}
                list="fs-client-opts"
              />
              <datalist id="fs-client-opts">
                {Array.from(new Set(options?.clients || [])).map(c => <option key={c} value={c} />)}
              </datalist>
            </div>
            <div>
              <Label required>DATE FROM</Label>
              <input type="date" value={form.date_from}
                min={options.min_date || ""} max={form.date_to || options.max_date || ""}
                onChange={e => set("date_from", e.target.value)} style={fieldStyle} />
            </div>
            <div>
              <Label required>DATE TO</Label>
              <input type="date" value={form.date_to}
                min={form.date_from || options.min_date || ""} max={options.max_date || ""}
                onChange={e => set("date_to", e.target.value)} style={fieldStyle} />
            </div>
          </div>

          <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "16px" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "12px" }}>
              OPTIONAL FILTERS
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <Label>STYLE NO</Label>
                <input type="text" value={form.style} placeholder="Partial match…"
                  onChange={e => set("style", e.target.value)} style={fieldStyle}
                  list="fs-style-opts" />
                <datalist id="fs-style-opts">
                  {Array.from(new Set(options.styles || [])).slice(0, 100).map(s => <option key={s} value={s} />)}
                </datalist>
              </div>
              <div>
                <Label>PO NUMBER</Label>
                <input type="text" value={form.po} placeholder="Partial match…"
                  onChange={e => set("po", e.target.value)} style={fieldStyle}
                  list="fs-po-opts" />
                <datalist id="fs-po-opts">
                  {Array.from(new Set(options.po_numbers || [])).slice(0, 100).map(p => <option key={p} value={p} />)}
                </datalist>
              </div>
            </div>
          </div>

          {canExport && (
            <div style={{ background: "var(--color-surface)", borderRadius: "7px", padding: "12px 16px", border: "1px solid var(--color-border)" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", marginBottom: "6px" }}>EXPORT QUERY</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", lineHeight: 1.8 }}>
                Factory: <span style={{ color: "var(--color-accent2)" }}>{form.factory}</span><br />
                Buyer: <span style={{ color: "var(--color-accent2)" }}>{form.client}</span><br />
                Period: <span style={{ color: "var(--color-accent2)" }}>{form.date_from} → {form.date_to}</span>
                {form.style && <><br />Style: <span style={{ color: "var(--color-accent2)" }}>{form.style}</span></>}
                {form.po    && <><br />PO: <span style={{ color: "var(--color-accent2)" }}>{form.po}</span></>}
              </div>
            </div>
          )}

          <button onClick={handleExport} disabled={!canExport || exporting} style={{
            background: canExport && !exporting ? "var(--color-success)" : "var(--color-border)",
            color: canExport && !exporting ? "#fff" : "var(--color-muted)",
            border: "none", padding: "11px 28px", borderRadius: "6px",
            fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
            letterSpacing: "0.06em", cursor: canExport && !exporting ? "pointer" : "not-allowed",
            alignSelf: "flex-start", transition: "all 0.15s",
            display: "flex", alignItems: "center", gap: "8px",
          }}>
            {exporting ? "GENERATING…" : "⬇  DOWNLOAD EXCEL SUMMARY"}
          </button>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// STAGE 3 — Retry
// ════════════════════════════════════════════════════════════════════════════════
function RetryStage({ lastBatchId, onRetryComplete }) {
  const { addLog } = useOutputStore();
  const [batchIdInput, setBatchInput] = useState(lastBatchId ? String(lastBatchId) : "");
  const [errorData, setErrorData]     = useState(null);   // full error-json response
  const [records, setRecords]         = useState([]);     // editable list
  const [loading, setLoading]         = useState(false);
  const [submitting, setSubmitting]   = useState(false);
  const [result, setResult]           = useState(null);   // retry response

  // Load error JSON from backend
  const handleLoadErrors = async () => {
    const pk = parseInt(batchIdInput, 10);
    if (!pk) return;
    setLoading(true);
    setErrorData(null); setRecords([]); setResult(null);
    addLog({ level: "info", message: `Loading error JSON for Batch #${pk}…` });
    try {
      const data = await fetchErrorJson(pk);
      setErrorData(data);
      setRecords(data.records || []);
      if (!data.total_blocked) {
        addLog({ level: "success", message: `Batch #${pk} has no blocked records — nothing to retry!` });
      } else {
        addLog({ level: "warning", message: `${data.total_blocked} blocked record(s) loaded for editing` });
      }
    } catch (e) {
      addLog({ level: "error", message: `Failed to load error JSON: ${e.response?.data?.detail || e.message}` });
    } finally {
      setLoading(false);
    }
  };

  // Download the error JSON as a file so user can edit offline
  const handleDownloadJson = () => {
    if (!errorData) {
      console.error("No errorData");
      return;
    }
    
    const blob = new Blob([JSON.stringify(errorData, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `batch-${errorData.batch_id}-errors.json`;
    a.click();
    URL.revokeObjectURL(url);
    addLog({ level: "info", message: `Downloaded error JSON for Batch #${errorData.batch_id}` });
  };

  // Upload a fixed JSON file
  const handleUploadJson = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        const recs   = parsed.records || parsed;
        const batchId = parsed.batch_id;
        if (batchId) setBatchInput(String(batchId));
        setErrorData(parsed);
        setRecords(Array.isArray(recs) ? recs : []);
        setResult(null);
        addLog({ level: "info", message: `Loaded ${Array.isArray(recs) ? recs.length : 0} record(s) from JSON file` });
      } catch {
        addLog({ level: "error", message: "Invalid JSON file" });
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  // Edit an individual field in a record inline
  const updateRecord = (idx, field, value) => {
    setRecords(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r));
  };

  // Submit fixed records to /retry/
  const handleSubmit = async () => {
    const pk = parseInt(batchIdInput, 10);
    if (!pk || !records.length) return;
    setSubmitting(true);
    setResult(null);
    addLog({ level: "info", message: `Submitting ${records.length} fixed record(s) for Batch #${pk}…` });
    try {
      const res = await retryBatch(pk, records);
      setResult(res);
      if (res.saved > 0) {
        addLog({ level: "success", message: `Retry: ${res.saved}/${res.submitted} record(s) saved to DB` });
        onRetryComplete?.(pk, res.saved);
      }
      if (res.still_blocked?.length > 0) {
        addLog({ level: "warning", message: `${res.still_blocked.length} record(s) still blocked after retry` });
        // Update records list to only the still-blocked ones for another pass
        setRecords(res.still_blocked);
      } else {
        setRecords([]);
      }
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    } finally {
      setSubmitting(false);
    }
  };

  const fileInputRef = useRef(null);

  // Editable fields the user commonly needs to fix
  const EDITABLE_FIELDS = [
    { key: "factory",         label: "Factory" },
    { key: "client",          label: "Client" },
    { key: "date_of_issue",   label: "Date of Issue" },
    { key: "inspection_type", label: "Inspection Type" },
    { key: "report_no",       label: "Report No" },
    { key: "ship_qty",        label: "Ship Qty" },
    { key: "audit_qty",       label: "Audit Qty" },
    { key: "style_no",        label: "Style No" },
    { key: "po_no",           label: "PO No" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px", maxWidth: "800px" }}>
      <div>
        <h2 style={hdr}>Stage 3 — Fix & Retry</h2>
        <p style={sub}>
          After extraction, some records may fail validation (e.g. missing factory name or date).
          Load the error report below, fix the fields inline, then re-submit to save them to the database.
        </p>
      </div>

      {/* Batch ID + load controls */}
      <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "0 0 200px" }}>
          <Label>BATCH ID</Label>
          <input
            type="number" value={batchIdInput}
            onChange={e => setBatchInput(e.target.value)}
            placeholder="e.g. 42"
            style={fieldStyle}
          />
        </div>
        <button onClick={handleLoadErrors} disabled={!batchIdInput || loading} style={{
          background: batchIdInput && !loading ? "var(--color-accent)" : "var(--color-border)",
          color: batchIdInput && !loading ? "#fff" : "var(--color-muted)",
          border: "none", padding: "10px 20px", borderRadius: "6px",
          fontFamily: "var(--font-mono)", fontSize: "11px", cursor: batchIdInput && !loading ? "pointer" : "not-allowed",
        }}>
          {loading ? "LOADING…" : "LOAD ERRORS"}
        </button>

        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", alignSelf: "center" }}>— or —</div>

        <button onClick={() => fileInputRef.current?.click()} style={{
          background: "transparent", border: "1px solid var(--color-border)",
          color: "var(--color-muted)", padding: "10px 18px", borderRadius: "6px",
          fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
        }}>
          📂 Upload Fixed JSON
        </button>
        <input ref={fileInputRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleUploadJson} />
      </div>

      {/* Error data header */}
      {errorData && (
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "16px", border: "1px solid var(--color-border)", display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", marginBottom: "4px" }}>
                Batch #{errorData.batch_id} — {records.length} record(s) to fix
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                {errorData.instructions}
              </div>
            </div>
            <button onClick={handleDownloadJson} style={{
              background: "transparent", border: "1px solid var(--color-border)",
              color: "var(--color-muted)", padding: "6px 14px", borderRadius: "5px",
              fontFamily: "var(--font-mono)", fontSize: "10px", cursor: "pointer", whiteSpace: "nowrap",
            }}>
              ⬇ Download JSON
            </button>
          </div>

          {/* Result banner */}
          {result && (
            <div style={{
              background: result.still_blocked?.length === 0 ? "rgba(34,211,160,0.08)" : "rgba(245,158,11,0.08)",
              border: `1px solid ${result.still_blocked?.length === 0 ? "rgba(34,211,160,0.2)" : "rgba(245,158,11,0.2)"}`,
              borderRadius: "6px", padding: "10px 14px",
              fontFamily: "var(--font-mono)", fontSize: "11px",
              color: result.still_blocked?.length === 0 ? "var(--color-success)" : "var(--color-warning)",
            }}>
              Submitted: {result.submitted} · Saved: {result.saved} · Still blocked: {result.still_blocked?.length ?? 0}
            </div>
          )}

          {/* Editable record table */}
          {records.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {records.map((rec, idx) => (
                <div key={idx} style={{
                  background: "var(--color-panel)", borderRadius: "7px",
                  border: "1px solid var(--color-border)",
                  borderLeft: "3px solid var(--color-error)",
                  padding: "14px 16px",
                }}>
                  {/* File name + errors */}
                  <div style={{ marginBottom: "10px" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)", marginBottom: "4px" }}>
                      📄 {rec.file_name}
                    </div>
                    {rec.blocking_errors?.map((err, i) => (
                      <div key={i} style={{ fontFamily: "var(--font-body)", fontSize: "10px", color: "var(--color-error)", lineHeight: 1.5 }}>
                        ⚠ {err}
                      </div>
                    ))}
                  </div>

                  {/* Editable fields */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
                    {EDITABLE_FIELDS.map(({ key, label }) => (
                      <div key={key}>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", marginBottom: "3px", letterSpacing: "0.06em" }}>
                          {label.toUpperCase()}
                        </div>
                        <input
                          type="text"
                          value={rec[key] || ""}
                          onChange={e => updateRecord(idx, key, e.target.value)}
                          style={{ ...fieldStyle, padding: "6px 8px", fontSize: "11px" }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <button onClick={handleSubmit} disabled={submitting} style={{
                background: submitting ? "var(--color-border)" : "var(--color-accent)",
                color: submitting ? "var(--color-muted)" : "#fff",
                border: "none", padding: "11px 28px", borderRadius: "6px",
                fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
                letterSpacing: "0.06em", cursor: submitting ? "not-allowed" : "pointer",
                alignSelf: "flex-start", transition: "all 0.15s",
              }}>
                {submitting ? "SUBMITTING…" : `↺  RETRY ${records.length} RECORD(S)`}
              </button>
            </div>
          )}

          {records.length === 0 && result?.still_blocked?.length === 0 && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-success)", padding: "8px 0" }}>
              ✓ All records have been saved successfully!
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// STAGE 4 — Logs
// ════════════════════════════════════════════════════════════════════════════════
function LogsStage({ lastBatchId }) {
  const { addLog } = useOutputStore();
  const [batchIdInput, setBatchInput] = useState(lastBatchId ? String(lastBatchId) : "");
  const [logsData, setLogsData]       = useState(null);
  const [loading, setLoading]         = useState(false);

  const handleLoad = async () => {
    const pk = parseInt(batchIdInput, 10);
    if (!pk) return;
    setLoading(true); setLogsData(null);
    addLog({ level: "info", message: `Loading logs for Batch #${pk}…` });
    try {
      const data = await fetchBatchLogs(pk);
      setLogsData(data);
      addLog({ level: "info", message: `Batch #${pk}: ${data.error_count} error(s), ${data.processed} processed / ${data.total_files} total` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to load logs: ${e.response?.data?.detail || e.message}` });
    } finally {
      setLoading(false);
    }
  };

  const STATUS_COLOR = {
    COMPLETED: "var(--color-success)", PARTIAL: "var(--color-warning)",
    FAILED: "var(--color-error)", PROCESSING: "var(--color-accent2)", PENDING: "var(--color-muted)",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "720px" }}>
      <div>
        <h2 style={hdr}>Stage 4 — Batch Logs</h2>
        <p style={sub}>View what happened during each upload — which files succeeded, which failed, and why.</p>
      </div>

      <div style={{ display: "flex", gap: "12px", alignItems: "flex-end" }}>
        <div style={{ flex: "0 0 200px" }}>
          <Label>BATCH ID</Label>
          <input type="number" value={batchIdInput}
            onChange={e => setBatchInput(e.target.value)}
            placeholder="e.g. 42" style={fieldStyle} />
        </div>
        <button onClick={handleLoad} disabled={!batchIdInput || loading} style={{
          background: batchIdInput && !loading ? "var(--color-accent)" : "var(--color-border)",
          color: batchIdInput && !loading ? "#fff" : "var(--color-muted)",
          border: "none", padding: "10px 20px", borderRadius: "6px",
          fontFamily: "var(--font-mono)", fontSize: "11px", cursor: batchIdInput && !loading ? "pointer" : "not-allowed",
        }}>
          {loading ? "LOADING…" : "LOAD LOGS"}
        </button>
      </div>

      {logsData && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
            {[
              ["Status",    logsData.status],
              ["Total",     logsData.total_files],
              ["Processed", logsData.processed],
              ["Failed",    logsData.failed],
            ].map(([label, val]) => (
              <div key={label} style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "7px", padding: "10px 14px" }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "5px" }}>
                  {label.toUpperCase()}
                </div>
                <div style={{
                  fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700,
                  color: label === "Status" ? (STATUS_COLOR[val] || "var(--color-text)") : "var(--color-text)",
                }}>
                  {val ?? "—"}
                </div>
              </div>
            ))}
          </div>

          {/* Error list */}
          {logsData.errors?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "6px" }}>
                FAILED FILES ({logsData.error_count})
              </div>
              {logsData.errors.map((err, i) => (
                <div key={i} style={{
                  padding: "10px 14px", background: "rgba(244,63,94,0.05)",
                  borderRadius: "6px", borderLeft: "2px solid var(--color-error)",
                }}>
                  {err.file_name && (
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-error)", marginBottom: "3px" }}>
                      📄 {err.file_name}
                    </div>
                  )}
                  <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)" }}>
                    {err.reason}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-success)", padding: "8px 0" }}>
              ✓ No errors — all files processed successfully
            </div>
          )}

          {/* Raw log */}
          {logsData.raw_error_log && (
            <details>
              <summary style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", cursor: "pointer", userSelect: "none", marginBottom: "8px" }}>
                RAW ERROR LOG
              </summary>
              <pre style={{
                fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)",
                whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7,
                background: "var(--color-surface)", borderRadius: "6px", padding: "12px 14px",
                border: "1px solid var(--color-border)", margin: 0,
              }}>
                {logsData.raw_error_log}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// Batch history sidebar
// ════════════════════════════════════════════════════════════════════════════════
function BatchHistory({ refreshKey, onSelectBatch }) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const user = useAuthStore(state => state.user);

  useEffect(() => {
    const abortController = new AbortController();

    if (!user?.user_id) {
      setBatches([]);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    fetchBatches({ signal: abortController.signal })
      .then(data => {
        if (abortController.signal.aborted) return;

        let list = Array.isArray(data)
          ? data
          : Array.isArray(data?.results)
          ? data.results
          : [];
        // Filter batches to only show those created by the logged-in user
        
        
        list = list.filter(b => b.created_by && b.created_by.id === user.user_id);
        
        setBatches(list);
        setLoading(false);
      })
      .catch(err => {
        if (abortController.signal.aborted) return;
        if (typeof addLog !== 'undefined') {
          addLog({ 
            level: "error", 
            message: `Failed to fetch batches: ${err.message}` 
          });
        } else {
          // Fallback to console
          console.error(`Failed to fetch batches: ${err.message}`);
        }
        setError(err.message);
        setBatches([]);
        setLoading(false);
      });
      return () => {
      abortController.abort();
    };
  }, [refreshKey, user?.user_id]);

  const STATUS_COLOR = {
    COMPLETED: "var(--color-success)", PARTIAL: "var(--color-warning)",
    FAILED: "var(--color-error)", PROCESSING: "var(--color-accent2)", PENDING: "var(--color-muted)",
  };

  return (
    <div style={{
      width: "260px", minWidth: "260px", background: "var(--color-surface)",
      borderLeft: "1px solid var(--color-border)", display: "flex", flexDirection: "column",
    }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--color-border)" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.1em", color: "var(--color-muted)" }}>
          UPLOAD HISTORY
        </span>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
        {loading && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", padding: "16px 8px" }}>
            Loading…
          </div>
        )}
        {!loading && batches.length === 0 && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", padding: "16px 8px", lineHeight: 1.8 }}>
            No batches yet.<br /><span style={{ opacity: 0.5 }}>Upload Excel files to begin.</span>
          </div>
        )}
        {batches.map(b => (
          <div key={b.id}
            onClick={() => onSelectBatch?.(b.id)}
            title="Click to view logs for this batch"
            style={{
              padding: "9px 12px", marginBottom: "4px",
              background: "var(--color-panel)", borderRadius: "6px", cursor: "pointer",
              border: "1px solid var(--color-border)",
              borderLeft: `3px solid ${STATUS_COLOR[b.status] || "var(--color-muted)"}`,
              transition: "opacity 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = "0.8"}
            onMouseLeave={e => e.currentTarget.style.opacity = "1"}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>#{b.id}</span>
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: "9px",
                color: STATUS_COLOR[b.status],
                background: `${STATUS_COLOR[b.status]}18`, padding: "1px 6px", borderRadius: "3px",
              }}>
                {b.status}
              </span>
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)" }}>
              {b.processed_files}/{b.total_files} files · {b.report_count || 0} records
            </div>
            {b.failed_files > 0 && (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-error)", marginTop: "2px" }}>
                ⚠ {b.failed_files} failed
              </div>
            )}
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", marginTop: "2px" }}>
              {new Date(b.created_at).toLocaleDateString()} {new Date(b.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════════
// Main page
// ════════════════════════════════════════════════════════════════════════════════
export default function FinalSummaryPage() {
  console.log("NEW BUILD LOADED"); 
  const [stage, setStage]         = useState("upload");
  const [lastBatchId, setLast]    = useState(null);
  const [lastCount, setCount]     = useState(0);
  const [failedCount, setFailed]  = useState(0);
  const [historyKey, setHistKey]  = useState(0);
  // Batch ID to pre-fill in Logs / Retry stages when clicking history sidebar
  const [sidebarBatch, setSidebarBatch] = useState(null);

  const handleBatchComplete = (batchId, reportCount, failed) => {
    setLast(batchId); setCount(reportCount); setFailed(failed);
    setHistKey(k => k + 1);
    // Auto-navigate: if failures, show retry; otherwise show export
    setStage(failed > 0 ? "retry" : "export");
  };

  const handleRetryComplete = (batchId, saved) => {
    setHistKey(k => k + 1);
    if (saved > 0) setStage("export");
  };

  const handleSidebarBatch = (batchId) => {
    setSidebarBatch(batchId);
    setStage("logs");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />

        {/* Main content */}
        <main style={{ flex: 1, background: "var(--color-bg)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Toolbar */}
          <div style={{
            height: "44px", background: "var(--color-surface)",
            borderBottom: "1px solid var(--color-border)",
            display: "flex", alignItems: "center", padding: "0 16px", gap: "8px",
          }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.1em", marginRight: "8px" }}>
              AUDIT SUMMARY
            </span>
            <StageTab label="1 · UPLOAD" active={stage === "upload"} onClick={() => setStage("upload")} />
            <StageTab label="2 · EXPORT" active={stage === "export"} onClick={() => setStage("export")} />
            <StageTab
              label="3 · RETRY"
              active={stage === "retry"}
              onClick={() => setStage("retry")}
              badge={failedCount}
            />
            <StageTab label="4 · LOGS"   active={stage === "logs"}   onClick={() => setStage("logs")} />
          </div>

          {/* Stage content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
            <div className="fade-up" key={stage}>
              {stage === "upload" && (
                <UploadStage onComplete={handleBatchComplete} />
              )}
              {stage === "export" && (
                <ExportStage lastBatchId={lastBatchId} lastCount={lastCount} />
              )}
              {stage === "retry" && (
                <RetryStage
                  lastBatchId={sidebarBatch || lastBatchId}
                  onRetryComplete={handleRetryComplete}
                />
              )}
              {stage === "logs" && (
                <LogsStage lastBatchId={sidebarBatch || lastBatchId} />
              )}
            </div>
          </div>
        </main>

        {/* Batch history sidebar — clicking a batch pre-fills Logs */}
        <BatchHistory
          refreshKey={historyKey}
          onSelectBatch={handleSidebarBatch}
        />
      </div>
    </div>
  );
}