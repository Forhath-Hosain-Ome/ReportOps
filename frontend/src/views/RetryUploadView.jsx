import { disp, body, mono, fieldStyle } from "../constants"
import { uploadFixedJson } from "../services/finalSummaryApi";
import { useOutputStore } from "../store/outputStore";
import { useState, useRef } from "react";

import { Label, SectionTitle, PrimaryBtn } from "../primitives/index";


function RetryUploadView() {
  const { addLog } = useOutputStore();
  const [batchId,  setBatchId]  = useState("");
  const [file,     setFile]     = useState(null);
  const [result,   setResult]   = useState(null);
  const [busy,     setBusy]     = useState(false);
  const [isDrag,   setIsDrag]   = useState(false);
  const fileInputRef = useRef(null);

  const pickFile = (f) => {
    if (!f) return;
    if (!f.name.endsWith(".json")) {
      addLog({ level: "error", message: "Only .json files are accepted." });
      return;
    }
    setFile(f);
    setResult(null);

    // Auto-detect batch_id: first try reading the JSON content (most reliable),
    // then fall back to parsing the filename e.g. batch-42-errors.json
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        if (parsed.batch_id) {
          setBatchId(String(parsed.batch_id));
          return;
        }
      } catch (err) {
        addLog({
            level: "error",
            message: `Parsing failed`,
            error: err?.message || err,
          });
        }
      
      // Filename fallback
      const m = f.name.match(/batch[-_](\d+)/i);
      if (m) setBatchId(m[1]);
    };
    reader.readAsText(f);
  };

  const handleDrop = (e) => {
    e.preventDefault(); setIsDrag(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  const handleSubmit = async () => {
    if (!batchId || !file || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading fixed JSON for Batch #${batchId}…` });
    try {
      const res = await uploadFixedJson(parseInt(batchId, 10), file);
      setResult(res);
      if (res.saved > 0)
        addLog({ level: "success", message: `${res.saved}/${res.submitted} record(s) saved to DB` });
      if (res.still_blocked?.length > 0)
        addLog({ level: "warning", message: `${res.still_blocked.length} record(s) still blocked` });
    } catch (e) {
      addLog({ level: "error", message: `Upload failed: ${e.response?.data?.detail || e.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "600px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>Upload Fixed JSON</h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Download the error JSON from <strong>Retry › Download Error JSON</strong>, fix the fields, then upload the corrected file here.
        </p>
      </div>

      <div>
        <Label required>BATCH ID</Label>
        <input type="number" value={batchId} placeholder="e.g. 42"
          onChange={e => setBatchId(e.target.value)} style={{ ...fieldStyle, width: "200px" }} />
      </div>

      {/* JSON drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "36px 24px", textAlign: "center",
          cursor: "pointer", background: isDrag ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={fileInputRef} type="file" accept=".json" style={{ display: "none" }}
          onChange={e => { pickFile(e.target.files?.[0]); e.target.value = ""; }} />
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>📂</div>
        {file ? (
          <>
            <div style={{ ...mono, fontSize: "12px", color: "var(--color-accent2)", marginBottom: "4px" }}>📄 {file.name}</div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
              {(file.size / 1024).toFixed(0)} KB · click to change
            </div>
          </>
        ) : (
          <>
            <div style={{ ...body, fontSize: "13px", color: "var(--color-text)", marginBottom: "6px" }}>
              Drag & drop fixed JSON file here, or click to browse
            </div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>.json · downloaded from Retry › Download Error JSON</div>
          </>
        )}
      </div>

      {/* Result banner */}
      {result && (
        <Card accent={result.still_blocked?.length === 0 ? "var(--color-success)" : "var(--color-warning)"}>
          <div style={{ ...mono, fontSize: "11px", color: result.still_blocked?.length === 0 ? "var(--color-success)" : "var(--color-warning)", lineHeight: 1.8 }}>
            Submitted: {result.submitted} · Saved: {result.saved} · Still blocked: {result.still_blocked?.length ?? 0}
          </div>
          {result.still_blocked?.length > 0 && (
            <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
              {result.still_blocked.map((r, i) => (
                <div key={i} style={{ ...body, fontSize: "11px", color: "var(--color-error)" }}>
                  ⚠ {r.file_name}: {Array.isArray(r.blocking_errors) ? r.blocking_errors.join("; ") : r.blocking_errors}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <PrimaryBtn onClick={handleSubmit} disabled={!batchId || !file || busy}>
        {busy ? "UPLOADING…" : "↺  SUBMIT FIXED RECORDS"}
      </PrimaryBtn>
    </div>
  );
}


export default RetryUploadView;