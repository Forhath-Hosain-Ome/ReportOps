import { disp, mono, body, STATUS_COLOR } from "../constants"
import AuditBatchRow from "../components/BatchRow";
import { Label, SectionTitle, PrimaryBtn } from "../primitives/index";

function AuditBatchList({ data, action, onAction }) {
  const batches = Array.isArray(data) ? data : (data?.results ?? []);
  const sorted  = [...batches].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ ...disp, fontSize: "16px", fontWeight: 700, margin: "0 0 8px", color: "var(--color-text)" }}>
        Batches <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({sorted.length})</span>
      </h2>

      {/* Column headers */}
      <div style={{
        display: "grid", gridTemplateColumns: "52px 1fr 90px 100px 90px 80px 96px",
        gap: "8px", padding: "4px 14px",
        ...mono, fontSize: "9px", letterSpacing: "0.08em", color: "var(--color-muted)",
      }}>
        <span>#</span>
        <span>PAIR / USER</span>
        <span>DATE</span>
        <span>STATUS</span>
        <span>FILES</span>
        <span>SUCCESS</span>
        <span style={{ textAlign: "right" }}>ACTIONS</span>
      </div>

      {sorted.length === 0 && (
        <div style={{ ...body, fontSize: "13px", color: "var(--color-muted)", padding: "32px 0", textAlign: "center" }}>
          No batches found.
        </div>
      )}

      {sorted.map(b => (
        <AuditBatchRow key={b.id} batch={b} action={action} onAction={onAction} />
      ))}
    </div>
  );
}


export default AuditBatchList;