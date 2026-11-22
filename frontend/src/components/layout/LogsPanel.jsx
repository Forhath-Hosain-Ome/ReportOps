import { useOutputStore } from "../../store/outputStore";


const LEVEL_COLORS = {
  info:    "var(--color-accent2)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  error:   "var(--color-error)",
};

const LEVEL_BG = {
  info:    "rgba(99,102,241,0.08)",
  success: "rgba(34,211,160,0.08)",
  warning: "rgba(245,158,11,0.08)",
  error:   "rgba(244,63,94,0.08)",
};

function fmt(iso) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
}

export default function LogsPanel() {
  const { logs, clearLogs } = useOutputStore();

  return (
    <aside
      style={{
        width: "240px",
        minWidth: "240px",
        background: "var(--color-surface)",
        borderRight: "1px solid var(--color-border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            fontWeight: 500,
            letterSpacing: "0.1em",
            color: "var(--color-muted)",
          }}
        >
          ACTIVITY LOG
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {logs.length > 0 && (
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "9px",
                color: "var(--color-accent)",
                background: "rgba(99,102,241,0.12)",
                padding: "1px 6px",
                borderRadius: "3px",
              }}
            >
              {logs.length}
            </span>
          )}
          <button
            onClick={clearLogs}
            title="Clear logs"
            style={{
              background: "none",
              border: "none",
              color: "var(--color-muted)",
              cursor: "pointer",
              fontSize: "11px",
              padding: "2px 4px",
              borderRadius: "3px",
              transition: "color 0.15s",
            }}
            onMouseEnter={(e) => e.target.style.color = "var(--color-error)"}
            onMouseLeave={(e) => e.target.style.color = "var(--color-muted)"}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Log entries */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
        {logs.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              color: "var(--color-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              lineHeight: 1.8,
            }}
          >
            No activity yet.<br />
            <span style={{ opacity: 0.5 }}>Actions will appear here.</span>
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className="fade-up"
              style={{
                marginBottom: "4px",
                padding: "7px 10px",
                borderRadius: "5px",
                background: LEVEL_BG[log.level] || "var(--color-panel)",
                borderLeft: `2px solid ${LEVEL_COLORS[log.level] || "var(--color-border)"}`,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "9px",
                  color: "var(--color-muted)",
                  marginBottom: "2px",
                }}
              >
                {fmt(log.ts)}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-body)",
                  fontSize: "11px",
                  color: LEVEL_COLORS[log.level] || "var(--color-text)",
                  lineHeight: 1.4,
                  wordBreak: "break-word",
                }}
              >
                {log.message}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
