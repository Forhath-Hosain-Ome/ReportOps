import { useOutputStore } from "../store/outputStore";
import { useState, useRef, useCallback } from "react";
import useAuditWs from "../hooks/useAuditWs";
import { uploadBatch } from "../services/finalSummaryApi";
import { fetchBatch } from "../services/finalSummaryApi";
import { disp, body, mono, fieldStyle } from "../constants"
import { Label, SectionTitle, PrimaryBtn } from "../primitives/index";

function UploadView({ data }) {
  const { addLog, setOutput } = useOutputStore();
  const options  = data?.options ?? { pairs: [], buyers: [], factories: [] };
  const pairs    = options.pairs ?? [];

  const [files,    setFiles]    = useState([]);
  const [pairId,   setPairId]   = useState("");
  const [date,     setDate]     = useState(new Date().toISOString().slice(0, 10));
  const [isDrag,   setIsDrag]   = useState(false);
  const [batchId,  setBatchId]  = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy,     setBusy]     = useState(false);
  const inputRef = useRef(null);

  // Derived: the selected pair object
  const selectedPair = pairs.find(p => String(p.id) === String(pairId));

  const addFiles = useCallback((incoming) => {
    const valid = [...incoming].filter(f =>
      f.name.toLowerCase().endsWith(".xlsx") || f.name.toLowerCase().endsWith(".xls")
    );
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...valid.filter(f => !names.has(f.name))];
    });
  }, [setFiles]);

  const onDrop = useCallback((e) => {
    e.preventDefault(); setIsDrag(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles, setIsDrag]);

  useAuditWs(batchId, {
    onProgress: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: async (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" });
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} record(s) saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} file(s) failed — use Retry › Download Error JSON to fix` });
      setBusy(false);
      // Navigate to batch detail
      try {
        const batch = await fetchBatch(msg.batch_id);
        setOutput("audit-batch", batch, `Batch #${msg.batch_id}`, { source: "audit" });
      } catch (err) {
          addLog({
            level: "error",
            message: `Batch fetch failed for ID ${msg.batch_id}`,
            error: err?.message || err,
          });}
        },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch error: ${msg.error_message}` });
      setBusy(false); setProgress(null); setBatchId(null);
    },
  });

  const handleUpload = async () => {
    if (!files.length || !pairId || !date || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading ${files.length} file(s) for pair #${pairId}…` });
    try {
      const res = await uploadBatch(files, pairId, date);
      setBatchId(res.batch_id);
      setProgress({ processed: 0, total: res.total_files, percent: 0, stage: "QUEUED" });
      addLog({ level: "success", message: `Batch #${res.batch_id} created — ${res.total_files} file(s) queued` });
    } catch (e) {
      const msg = e.response?.data?.files?.[0] || e.response?.data?.pair_id?.[0] || e.response?.data?.detail || e.message;
      addLog({ level: "error", message: `Upload failed: ${msg}` });
      setBusy(false);
    }
  };

  const canUpload = files.length > 0 && pairId && date && !busy;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "660px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
          Upload Excel Files
        </h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Select an active buyer–factory pair, set the inspection date, then upload one or many audit report Excel files.
          The pair determines which extractor and template are used.
        </p>
      </div>

      {/* Pair + date selectors */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        <div>
          <Label required>BUYER–FACTORY PAIR</Label>
          <select
            value={pairId}
            onChange={e => setPairId(e.target.value)}
            style={{ ...fieldStyle }}
            disabled={busy}
          >
            <option value="">— Select pair —</option>
            {pairs.map(p => (
              <option key={p.id} value={p.id}>
                {p["buyer__name"]} × {p["factory__name"]} [{p.report_type}]
              </option>
            ))}
          </select>
          {selectedPair && (
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", marginTop: "5px" }}>
              Allowed: {selectedPair.available_reports?.join(", ") || "—"}
            </div>
          )}
        </div>
        <div>
          <Label required>INSPECTION DATE</Label>
          <input
            type="date" value={date}
            onChange={e => setDate(e.target.value)}
            style={fieldStyle}
            disabled={busy}
          />
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "44px 24px", textAlign: "center",
          cursor: busy ? "not-allowed" : "pointer",
          background: isDrag ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={inputRef} type="file" accept=".xlsx,.xls" multiple style={{ display: "none" }}
          onChange={e => { addFiles(e.target.files); e.target.value = ""; }} />
        <div style={{ fontSize: "30px", marginBottom: "10px" }}>📊</div>
        <div style={{ ...body, fontSize: "14px", color: "var(--color-text)", marginBottom: "6px" }}>
          Drag & drop Excel files here, or click to browse
        </div>
        <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
          .xlsx and .xls · 50 MB per file max · Multiple files supported
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          <SectionTitle>{files.length} FILE(S) SELECTED</SectionTitle>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "7px 12px", background: "var(--color-surface)",
              borderRadius: "5px", border: "1px solid var(--color-border)",
            }}>
              <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)" }}>📄 {f.name}</span>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                {!busy && (
                  <button
                    onClick={e => { e.stopPropagation(); setFiles(prev => prev.filter((_, j) => j !== i)); }}
                    style={{ background: "none", border: "none", color: "var(--color-error)", cursor: "pointer", fontSize: "12px" }}
                  >✕</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar */}
      {progress && (
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "14px", border: "1px solid var(--color-border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
            <span style={{ ...mono, fontSize: "10px", color: "var(--color-accent2)" }}>{progress.stage}</span>
            <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{progress.processed}/{progress.total}</span>
          </div>
          <div style={{ height: "4px", background: "var(--color-border)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${progress.percent}%`,
              background: progress.stage === "DONE" ? "var(--color-success)" : "var(--color-accent)",
              borderRadius: "2px", transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      )}

      <PrimaryBtn onClick={handleUpload} disabled={!canUpload}>
        {busy ? "PROCESSING…" : "UPLOAD & EXTRACT"}
      </PrimaryBtn>
    </div>
  );
}

export default UploadView;