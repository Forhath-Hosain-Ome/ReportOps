import { useState, useEffect, useRef } from "react";
import { Btn, Section, IconBtn2 } from "../primitives/index";

function DownloadDropdown({ batchId, hasExcel, reports = [], reportCount = 0, onAction }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const activeReportCount = reportCount || reports.length || 0;

  const items = [
    hasExcel && { key: "excel", label: "Excel (.xlsx)", icon: "📊", desc: "All reports in this batch" },
    activeReportCount > 0 && { key: "pdfs", label: "Reports (.pdf)", icon: "📄", desc: `${activeReportCount} renamed PDF(s)` },
    activeReportCount > 0 && { key: "certificates", label: "Reports (.docx)", icon: "📝", desc: `${activeReportCount} DOCX report(s)` },
    hasExcel && activeReportCount > 0 && { key: "all", label: "All files", icon: "📦", desc: "PDF, DOCX, and Excel for batch" },
  ].filter(Boolean);

  if (!items.length) return <IconBtn2 title="No downloads available" disabled>⬇</IconBtn2>;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <IconBtn2 title="Downloads" onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} active={open}>
        ⬇
      </IconBtn2>
      {open && (
        <div style={{
          position: "absolute", right: 0, top: "calc(100% + 4px)",
          background: "var(--color-surface)", border: "1px solid var(--color-border)",
          borderRadius: "8px", minWidth: "190px", zIndex: 50,
          boxShadow: "0 8px 24px rgba(0,0,0,0.3)", overflow: "hidden",
        }}>
          <div className="desc" style={{ padding: "6px 12px 4px", letterSpacing: "0.08em", borderBottom: "1px solid var(--color-border)" }}>
            DOWNLOAD
          </div>
          {items.map((item) => (
            <button
              key={item.key}
              onClick={(e) => { e.stopPropagation(); setOpen(false); onAction(item.key); }}
              style={{ width: "100%", background: "none", border: "none", padding: "9px 14px", display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", textAlign: "left" }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--color-panel)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "none"}
            >
              <span style={{ fontSize: "14px" }}>{item.icon}</span>
              <div>
                <div className="label">{item.label}</div>
                <div className="desc">{item.desc}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default DownloadDropdown;