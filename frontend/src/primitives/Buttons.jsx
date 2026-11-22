import clsx from "clsx";

export function PrimaryBtn({ children, onClick, disabled, danger }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`disp primary-btn ${
        disabled
        ? "primary-btn--disabled"
        : danger
        ? "primary-btn--danger"
        : "primary-btn--default"
      }`}
    >
      {children}
    </button>
  );
}

export function GhostBtn({ children, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`mono ghost-btn`}>
      {children}
    </button>
  );
}

export function IconBtn({ children, onClick, title, disabled }) {
  return (
    <button onClick={onClick} title={title} disabled={disabled} className={` icon-btn`}>
      {children}
    </button>
  );
}

export function IconBtn2({ children, onClick, title, active, disabled, color }) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={`
        text-[13px] w-7 h-7 rounded-[5px] flex items-center justify-center transition-all duration-[120] shrink-0 
        ${active
          ? "rgba(99,102,241,0.12) border-rgba(99,102,241,0.3) text-[var(--color-accent2)]"
          : "bg-transparent border-[var(--color-border)] text-[var(--color-muted)]"
        }
        ${
          disabled
          ? "opacity-35 cursor-not-allowed"
          : "cursor-pointer"
        }
        ${disabled && !active && !color
          ? "text-[var(--color-muted)]"
          : ""
        }
      `
      }
      onMouseEnter={(e) => { if (!disabled && !active) e.currentTarget.style.background = "var(--color-panel)"; }}
      onMouseLeave={(e) => { if (!disabled && !active) e.currentTarget.style.background = "transparent"; }}
    >
      {children}
    </button>
  );
}

export function ErrBtn({ handleDownload, busy, batchId }) {
  return (
    <button
          onClick={handleDownload}
          disabled={busy}
          title={`Download error JSON for Batch #${batchId}`}
          className="download-btn"
        >
          {busy ? "…" : `⬇ Batch #${batchId}`}
        </button>
  );
}

export function Btn({ children, onClick, accent }) {
  return (
    <button onClick={onClick} style={{ background: accent ? "rgba(99,102,241,0.12)" : "var(--color-surface)", border: `1px solid ${accent ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`, color: accent ? "var(--color-accent2)" : "var(--color-muted)", padding: "5px 14px", borderRadius: "5px", fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer", transition: "all 0.15s" }}>
      {children}
    </button>
  );
}

export function ApiMenuButton({ ep, active, onSelect, mc }) {
  return (
    <button
      onClick={() => onSelect(ep)}
      className={clsx(
        "w-full flex items-center gap-2 text-left px-[10px] py-2 rounded-[5px] mb-[2px] transition-all border",
        active
          ? "bg-[var(--color-panel)] border-[var(--color-border)] border-l-2 border-l-[var(--color-accent)]"
          : "bg-transparent border-transparent hover:bg-[var(--color-panel)]"
      )}
    >
      {/* METHOD */}
      <span
        className="text-[8px] font-medium px-1.25 py-px rounded-[3px] min-w-8 text-center tracking-[0.05em]"
        style={{
          background: mc.bg,
          color: mc.text,
        }}
      >
        {ep.method}
      </span>

      {/* ICON */}
      <span className="text-[11px] opacity-50">{ep.icon}</span>

      {/* TEXT */}
      <div className="flex-1 min-w-0">
        <div
          className={clsx(
            "text-[12px] font-body truncate",
            active ? "text-[var(--color-text)] font-medium" : "text-muted"
          )}
        >
          {ep.label}
        </div>

        <div className="text-[9px] text-muted opacity-60 truncate">
          {ep.path}
        </div>
      </div>
    </button>
  );
}

export function CollapsedButton({ label, isCollapsed, onToggle }) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between rounded-sm px-2 py-1.25"
    >
      <span className="text-[9px] tracking-[0.12em] font-medium text-muted">
        {label}
      </span>

      <span className="text-[9px] text-muted">
        {isCollapsed ? "▶" : "▼"}
      </span>
    </button>
  );
}