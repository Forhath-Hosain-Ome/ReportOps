import AuditOutput from "../audit/AuditOutput";
import { useOutputStore } from "../../store/outputStore";
import BatchOutput from "../batch/BatchOutput";
import ReportOutput from "../reports/ReportOutput";
import TopFiveOutput from "../top_five/TopFiveOutput"; // ← new import

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export default function OutputPanel() {
  const { output, outputTitle, isLoading, clearOutput } = useOutputStore();

  // Types that support JSON export
  const exportableTypes = ["batch", "report", "logs", "batch-list", "report-list", "top5-job-list", "top5-job"];

  return (
    <main className="flex flex-1 flex-col w-min-0 overflow-hidden"
      style={{
        background: "var(--color-bg)",
      }}
    >
      {/* Output toolbar */}
      <div 
        style={{
          height: "44px",
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          gap: "12px",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            letterSpacing: "0.08em",
            color: "var(--color-muted)",
            flex: 1,
          }}
        >
          OUTPUT
          {outputTitle && (
            <span style={{ color: "var(--color-accent2)", marginLeft: "8px" }}>
              · {outputTitle}
            </span>
          )}
        </span>

        {output && (
          <>
            {exportableTypes.includes(output?.type) && (
              <button
                onClick={() => {
                  const blob = new Blob([JSON.stringify(output.data, null, 2)], {
                    type: "application/json",
                  });
                  saveBlob(blob, `${output.type}-export.json`);
                }}
                style={{
                  background: "rgba(99,102,241,0.1)",
                  border: "1px solid rgba(99,102,241,0.25)",
                  color: "var(--color-accent2)",
                  padding: "3px 12px",
                  borderRadius: "4px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  letterSpacing: "0.06em",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = "rgba(99,102,241,0.2)"}
                onMouseLeave={(e) => e.currentTarget.style.background = "rgba(99,102,241,0.1)"}
              >
                ⬇ EXPORT JSON
              </button>
            )}

            <button
              onClick={clearOutput}
              style={{
                background: "transparent",
                border: "1px solid var(--color-border)",
                color: "var(--color-muted)",
                padding: "3px 12px",
                borderRadius: "4px",
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                letterSpacing: "0.06em",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--color-error)";
                e.currentTarget.style.color = "var(--color-error)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--color-border)";
                e.currentTarget.style.color = "var(--color-muted)";
              }}
            >
              ✕ CLEAR
            </button>
          </>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
         {isLoading ? (
            <LoadingState />
          ) : !output ? (
            <EmptyState />
          ) : output.source === "audit" ? (
            <AuditOutput output={output} />
          ) : output.type === "batch" || output.type === "batch-list" || output.type === "logs" || output.type === "batch-progress" || output.type === "image-settings" ? (
            <BatchOutput output={output} />
          ) : output.type === "report" || output.type === "report-list" ? (
            <ReportOutput output={output} />
          ) : output.type === "top5-upload" || output.type === "top5-job-list" || output.type === "top5-job" ? (
            <TopFiveOutput output={output} />
          ) : (
            <pre style={{fontFamily:"var(--font-mono)",fontSize:"12px",color:"var(--color-text)",whiteSpace:"pre-wrap",wordBreak:"break-word",lineHeight:1.7}}>
              {JSON.stringify(output.data, null, 2)}
            </pre>
          )}
      </div>
    </main>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: "12px",
        opacity: 0.35,
      }}
    >
      <div
        style={{
          width: "48px",
          height: "48px",
          border: "1.5px solid var(--color-border)",
          borderRadius: "12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "20px",
        }}
      >
        ◎
      </div>
      <span className="text-[11px] tracking-[0.08em]"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          letterSpacing: "0.08em",
          color: "var(--color-muted)",
        }}
      >
        SELECT AN ENDPOINT
      </span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-2.5" >
      {[100, 80, 90, 60].map((w, i) => (
        <div
          key={i}
          className="skeleton rounded-sm h-4.5 "
          style={{ width: `${w}%` }}
        />
      ))}
    </div>
  );
}
