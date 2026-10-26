import { useState, useCallback, useEffect, useRef } from "react";
import { useOutputStore } from "../store/outputStore";
import { useWsProgress } from "../hooks/useWsProgress";
import {
  uploadBatch as uploadBatchPuma,
  fetchBatch as fetchBatchPuma,
} from "../services/pumaApi";
import {
  uploadBatch as uploadBatchImage,
  fetchBatch as fetchBatchImage,
} from "../services/defectImageApi";
import { Btn, Section } from "../primitives/index";
import { pickBtnStyle, inputStyle } from "../constants"

export default function UploadForm({ initData = {}, source = "puma" }) {
  const getDefaultDate = () => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
  };
  const { addLog, setOutput, setLoading } = useOutputStore();
  const uploadLock = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [selectionErrors, setSelectionErrors] = useState([]);
  const [files, setFiles]       = useState([]);
  const [date, setDate]         = useState(initData.date || getDefaultDate());
  const [style, setStyle]       = useState(initData.style || "");
  const [isRenamedFile, setIsRenamedFile] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [batchId, setBatch]     = useState(initData.batch_id ?? null);
  const [progress, setProgress] = useState(initData.progress ?? null);

  // Refs for inputs
  const folderInputRef = useRef(null);
  const fileInputRef   = useRef(null);

  const isImageUpload = source === "image";
  const serviceUpload = isImageUpload ? uploadBatchImage : uploadBatchPuma;
  const serviceFetchBatch = isImageUpload ? fetchBatchImage : fetchBatchPuma;

  // ✅ Add these two lines
  const serviceFetchBatchRef = useRef(serviceFetchBatch);
  useEffect(() => { serviceFetchBatchRef.current = serviceFetchBatch; }, [serviceFetchBatch]);

  // Keep store in sync so progress survives remounts
  const syncStore = useCallback((patch) => {
    useOutputStore.setState((s) => ({
      output: s.output ? { ...s.output, ...patch } : s.output,
    }));
  }, []);

  // ── File collection helpers ───────────────────────────────────────────────

  // Process a FileList (from input or DataTransfer), preserving webkitRelativePath
  const processFileList = useCallback((fileList) => {
    if (uploadLock.current) return;
    const accepted = [];
    const rejected = [];
    const validExts = isImageUpload
      ? new Set([".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"])
      : new Set([".pdf"]);

    for (const file of fileList) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (validExts.has(ext) && file.size > 0 && file.size <= 50 * 1024 * 1024) {
        accepted.push(file);
      } else { rejected.push(`${file.name}: unsupported, empty, or larger than 50 MB`); }
    }
    setSelectionErrors(rejected);
    if (accepted.length > 0) setFiles((previous) => isImageUpload ? [...new Map([...previous, ...accepted].map((f) => [f.webkitRelativePath || f.name, f])).values()] : accepted);
  }, [isImageUpload]);

  // ── Drag-and-drop ─────────────────────────────────────────────────────────
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    if (uploadLock.current) { e.preventDefault(); return; }
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const items = e.dataTransfer?.items;
    if (!items) return;

    // Use DataTransferItemList to get webkitGetAsEntry for folder traversal
    const allFiles = [];
    const promises = [];

    const traverseEntry = (entry) => {
      return new Promise((resolve) => {
        if (entry.isFile) {
          entry.file((file) => {
            // Reconstruct a path that mirrors webkitRelativePath
            // entry.fullPath starts with "/" so we strip it
            const relativePath = entry.fullPath.replace(/^\//, "");
            // Attach the relative path so upload knows folder structure
            Object.defineProperty(file, "webkitRelativePath", {
              value: relativePath,
              writable: false,
            });
            allFiles.push(file);
            resolve();
          }, resolve);
        } else if (entry.isDirectory) {
          const reader = entry.createReader();
          const readAll = () => {
            reader.readEntries((entries) => {
              if (entries.length === 0) { resolve(); return; }
              Promise.all(entries.map(traverseEntry)).then(() => readAll());
            }, resolve);
          };
          readAll();
        } else {
          resolve();
        }
      });
    };

    for (const item of items) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) promises.push(traverseEntry(entry));
    }

    Promise.all(promises).then(() => processFileList(allFiles));
  }, [processFileList]);

  // ── Folder/file input changes ─────────────────────────────────────────────
  const handleFolderInputChange = useCallback((e) => {
    processFileList(e.target.files);
    e.target.value = ""; // allow re-selecting same folder
  }, [processFileList]);

  const handleFileInputChange = useCallback((e) => {
    processFileList(e.target.files);
    e.target.value = "";
  }, [processFileList]);

  // ── Derived folder summary ────────────────────────────────────────────────
  const folderSummary = (() => {
    if (!files.length) return null;
    const byFolder = {};
    for (const f of files) {
      const rel  = f.webkitRelativePath || f.name;
      const parts = rel.split("/");
      const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : "(root)";
      if (!byFolder[folder]) byFolder[folder] = 0;
      byFolder[folder]++;
    }
    return byFolder;
  })();

  // ── Upload handler ────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!files.length || batchId || uploadLock.current) return;
    uploadLock.current = true;
    setUploading(true);
    setLoading(true);

    addLog({
      level: "info",
      message: `Uploading ${files.length} file(s) from ${Object.keys(folderSummary || {}).length} folder(s)…`,
    });

    try {
      let res;

      if (isImageUpload) {
        // Extract relative paths from webkitRelativePath, falling back to filename
        const paths = files.map((f) => f.webkitRelativePath || f.name);
        res = await serviceUpload(files, paths, date, style, isRenamedFile);
      } else {
        res = await serviceUpload(files);
      }

      const totalItems = res.total_pdfs ?? res.total_folders ?? files.length;
      const initialProgress = { processed: 0, total: totalItems, percent: 0, stage: "QUEUED" };
      setBatch(res.batch_id);
      setProgress(initialProgress);
      setOutput(
        "batch-progress",
        { ...res, batch_id: res.batch_id, progress: initialProgress, source, date, style },
        `Batch #${res.batch_id}`,
        { source }
      );
      addLog({
        level: "success",
        message: `Batch #${res.batch_id} created — ${totalItems} folder(s) queued`,
      });
      setLoading(false);
    } catch (e) {
      const detail = e.response?.data?.detail || e.response?.data || e.message;
      addLog({
        level: "error",
        message: `Upload failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
      });
      setLoading(false);
    } finally { uploadLock.current = false; setUploading(false); }
  };

  useWsProgress(batchId, {
    source,
    onProgress: (msg) => {
      const p = { processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage };
      setProgress(p);
      syncStore({ progress: p });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: async (msg) => {
      const p = { processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" };
      setProgress(p);
      syncStore({ progress: p });
      addLog({ level: "success", message: `Batch #${msg.batch_id} ${msg.status} — ${msg.report_count} report(s) saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} folder(s) failed in Batch #${msg.batch_id}` });
      const full = await serviceFetchBatchRef.current(msg.batch_id);
      setOutput("batch", full, `Batch #${msg.batch_id}`, { source });
      setBatch(null);
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch #${msg.batch_id} error: ${msg.error_message}` });
      setProgress(null);
      syncStore({ progress: null });
    },
  });

  useEffect(() => {
    if (!batchId || source !== "image") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const full = await serviceFetchBatchRef.current(batchId);
        if (cancelled) return;
        setProgress({ processed: full.processed_folders, total: full.total_folders,
          percent: full.progress_percent, stage: full.dispatch_state });
        if (["COMPLETED", "PARTIAL", "FAILED"].includes(full.status) || ["FAILED", "UNKNOWN"].includes(full.dispatch_state)) {
          setOutput("batch", full, `Batch #${batchId}`, { source });
          setBatch(null);
        }
      } catch (error) { if (!cancelled) addLog({ level: "error", message: error.message }); }
    };
    const timer = setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [batchId, source, setOutput, addLog]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
        {isImageUpload ? "Upload Image Folders" : "Upload PDFs"}
      </h2>

      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${isDragOver ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px",
          padding: "40px 24px",
          textAlign: "center",
          background: isDragOver ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>
          {isImageUpload ? "🗂️" : "📄"}
        </div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)", marginBottom: "6px" }}>
          {isImageUpload
            ? "Drag & drop image folders here"
            : "Drag & drop PDF files here"}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", opacity: 0.7, marginBottom: "16px" }}>
          {isImageUpload
            ? "Each folder becomes one DOCX report · 50 MB per file max"
            : "PDF only · 50 MB per file max"}
        </div>

        {/* Hidden inputs */}
        {isImageUpload && (
          <>
            {/* Folder picker — webkitdirectory lets the user pick an entire folder */}
            <input
              ref={folderInputRef}
              type="file"
              style={{ display: "none" }}
              // These attributes MUST be set as strings on the DOM element —
              // React doesn't support webkitdirectory as a prop on <input>.
              onChange={handleFolderInputChange}
              multiple
            />
            {/* Fallback: individual file picker */}
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: "none" }}
              accept="image/*"
              onChange={handleFileInputChange}
              multiple
            />
          </>
        )}
        {!isImageUpload && (
          <input
            ref={fileInputRef}
            type="file"
            style={{ display: "none" }}
            accept=".pdf"
            onChange={handleFileInputChange}
            multiple
          />
        )}

        <div style={{ display: "flex", gap: "8px", justifyContent: "center", flexWrap: "wrap" }}>
          {isImageUpload && (
            <button
              disabled={uploading || !!batchId}
              onClick={() => {
                // Set webkitdirectory imperatively — avoids React JSX limitation
                const input = folderInputRef.current;
                if (input) {
                  input.setAttribute("webkitdirectory", "");
                  input.setAttribute("directory", "");
                  input.click();
                }
              }}
              style={pickBtnStyle}
            >
              📁 Select Folder(s)
            </button>
          )}
          <button
            disabled={uploading || !!batchId}
            onClick={() => fileInputRef.current?.click()}
            style={pickBtnStyle}
          >
            {isImageUpload ? "🖼️ Select Images" : "📄 Select PDFs"}
          </button>
        </div>
      </div>

      {/* Date + Rename File Checkbox + Style inputs for image mode */}
      {isImageUpload && (
        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", alignItems: "flex-start" }}>
          <label style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)", display: "flex", flexDirection: "column", gap: "6px" }}>
            Inspection Date
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              style={inputStyle}
            />
          </label>
          <label style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)", display: "flex", flexDirection: "column", gap: "6px", cursor: "pointer" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="checkbox"
                checked={isRenamedFile}
                onChange={(e) => setIsRenamedFile(e.target.checked)}
                style={{ accentColor: "var(--color-accent)", width: "14px", height: "14px", marginTop: "2px" }}
              />
              Show File Names in DOCX
            </span>
          </label>
          <label style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)", display: "flex", flexDirection: "column", gap: "6px" }}>
            Style Name (optional)
            <input
              type="text"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              placeholder="e.g. ABC-001"
              style={inputStyle}
            />
          </label>
        </div>
      )}

      {selectionErrors.length > 0 && <div role="alert">{selectionErrors.map((message) => <p key={message}>{message}</p>)}</div>}
      {/* Folder/file preview */}
      {folderSummary && Object.keys(folderSummary).length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
            {isImageUpload
              ? `${Object.keys(folderSummary).length} FOLDER(S) · ${files.length} IMAGE(S) TOTAL`
              : `${files.length} FILE(S) SELECTED`}
          </div>
          {Object.entries(folderSummary).map(([folder, count]) => (
            <div
              key={folder}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "7px 12px",
                background: "var(--color-surface)",
                borderRadius: "5px",
                border: "1px solid var(--color-border)",
              }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
                {isImageUpload ? "📁 " : "📄 "}{folder}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                {count} {isImageUpload ? "image(s)" : "file(s)"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar */}
      {progress && (
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
            <div
              style={{
                height: "100%",
                width: `${progress.percent}%`,
                background: progress.stage === "DONE" ? "var(--color-success)" : "var(--color-accent)",
                borderRadius: "2px",
                transition: "width 0.5s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!files.length || !!batchId || uploading}
        style={{
          background: files.length && !batchId ? "var(--color-accent)" : "var(--color-border)",
          color: files.length && !batchId ? "#fff" : "var(--color-muted)",
          border: "none",
          padding: "10px 24px",
          borderRadius: "6px",
          fontFamily: "var(--font-display)",
          fontSize: "13px",
          fontWeight: 600,
          letterSpacing: "0.06em",
          cursor: files.length && !batchId ? "pointer" : "not-allowed",
          transition: "all 0.15s",
          alignSelf: "flex-start",
        }}
      >
        {batchId ? "PROCESSING…" : "UPLOAD & PROCESS"}
      </button>
    </div>
  );
}