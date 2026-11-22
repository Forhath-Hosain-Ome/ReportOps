import { mono, disp, body, fieldStyle } from "../constants"
import { useOutputStore } from "../store/outputStore";
import { useState } from "react";
import { searchBlocked } from "../services/finalSummaryApi";
import { Label, SectionTitle, PrimaryBtn } from "../primitives/index";

function RetrySearchView() {
  const { addLog } = useOutputStore();
  const [date,    setDate]    = useState("");
  const [style,   setStyle]   = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    setLoading(true);
    addLog({ level: "info", message: "Searching blocked records…" });
    try {
      const params = {};
      if (date)  params.date  = date;
      if (style) params.style = style;
      const data = await searchBlocked(params);
      setResults(data);
      addLog({ level: "success", message: `Found ${data.count} blocked record(s)` });
    } catch (e) {
      addLog({ level: "error", message: `Search failed: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "720px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>Search Blocked Records</h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Find records that failed validation. Download the error JSON for the relevant batch, fix the fields, then re-upload via <strong>Upload Fixed JSON</strong>.
        </p>
      </div>

      <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
        <div>
          <Label>DATE</Label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} style={{ ...fieldStyle, width: "180px" }} />
        </div>
        <div>
          <Label>STYLE NO</Label>
          <input type="text" value={style} placeholder="Partial match…" onChange={e => setStyle(e.target.value)} style={{ ...fieldStyle, width: "200px" }} />
        </div>
        <PrimaryBtn onClick={handleSearch} disabled={loading}>
          {loading ? "SEARCHING…" : "⌕  SEARCH"}
        </PrimaryBtn>
      </div>

      {results && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <SectionTitle>{results.count} RESULT(S)</SectionTitle>
          {results.records.length === 0 && (
            <div style={{ ...mono, fontSize: "11px", color: "var(--color-success)" }}>✓ No blocked records found.</div>
          )}
          {results.records.map((r, i) => (
            <Card key={i} accent="var(--color-error)">
              <div style={{ display: "flex", gap: "12px", alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)", marginBottom: "4px" }}>
                    📄 {r.file_name}
                  </div>
                  <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", marginBottom: "6px" }}>
                    Batch #{r.batch_id} · {r.factory} · {r.style_no} · {r.date_of_issue}
                  </div>
                  {r.blocking_errors.map((err, j) => (
                    <div key={j} style={{ ...body, fontSize: "11px", color: "var(--color-error)", lineHeight: 1.5 }}>⚠ {err}</div>
                  ))}
                  {r.cross_check_warnings?.map((w, j) => (
                    <div key={j} style={{ ...body, fontSize: "11px", color: "var(--color-warning)", lineHeight: 1.5, marginTop: "2px" }}>⚡ {w}</div>
                  ))}
                </div>
                {/* Download error JSON for this batch directly from the search result */}
                <DownloadErrBtn batchId={r.batch_id} addLog={addLog} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default RetrySearchView;