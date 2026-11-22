import { useOutputStore } from "../store/outputStore";
import { useState } from "react";
import { disp, body, mono, fieldStyle, saveBlob } from "../constants"
import { Label, SectionTitle, PrimaryBtn, Card } from "../primitives/index";
import { downloadSummary } from "../services/finalSummaryApi";


function ExportView({ data }) {
  const { addLog } = useOutputStore();
  const options   = data?.options ?? {};
  const [form, setForm] = useState({ factory: "", client: "", date_from: "", date_to: "", style: "", po: "" });
  const [exporting, setExporting] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const canExport = form.factory && form.client && form.date_from && form.date_to;

  const handleExport = async () => {
    if (!canExport || exporting) return;
    setExporting(true);
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
      saveBlob(blob, name);
      addLog({ level: "success", message: `Downloaded: ${name}` });
      const skipped = headers["x-skipped-stages"];
      if (skipped) {
        addLog({
          level: "warning",
          message: `Note: no template configured yet for stage(s) [${skipped}] — those records were left out of this file.`,
        });
      }
    } catch (e) {
      const err = e.response?.data;
      // err may be a Blob (responseType mismatch) or JSON
      if (err instanceof Blob) {
        const text = await err.text();
        try { addLog({ level: "error", message: `Export failed: ${JSON.parse(text)?.detail}` }); }
        catch { addLog({ level: "error", message: `Export failed: ${text}` }); }
      } else {
        addLog({ level: "error", message: `Export failed: ${err?.detail || e.message}` });
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex flex-col gap-5.5 w-max-[660px]">
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
          Download Summary
        </h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Filter by factory, buyer, and date range to generate a grouped Excel summary with defect analysis.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-[3.5]" >
        <div>
          <Label required>FACTORY</Label>
          <input type="text" value={form.factory} placeholder="Type or select…"
            onChange={e => set("factory", e.target.value)} style={fieldStyle} list="ex-factory-opts" />
          <datalist id="ex-factory-opts">
            {(options.factories ?? []).map(f => <option key={f} value={f} />)}
          </datalist>
        </div>
        <div>
          <Label required>BUYER / CLIENT</Label>
          <input type="text" value={form.client} placeholder="Type or select…"
            onChange={e => set("client", e.target.value)} style={fieldStyle} list="ex-client-opts" />
          <datalist id="ex-client-opts">
            {(options.clients ?? []).map(c => <option key={c} value={c} />)}
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

      {/* Optional filters */}
      <div>
        <SectionTitle>OPTIONAL FILTERS</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
          <div>
            <Label>STYLE NO</Label>
            <input type="text" value={form.style} placeholder="Partial match…"
              onChange={e => set("style", e.target.value)} style={fieldStyle} list="ex-style-opts" />
            <datalist id="ex-style-opts">
              {(options.styles ?? []).slice(0, 100).map(s => <option key={s} value={s} />)}
            </datalist>
          </div>
          <div>
            <Label>PO NUMBER</Label>
            <input type="text" value={form.po} placeholder="Partial match…"
              onChange={e => set("po", e.target.value)} style={fieldStyle} list="ex-po-opts" />
            <datalist id="ex-po-opts">
              {(options.po_numbers ?? []).slice(0, 100).map(p => <option key={p} value={p} />)}
            </datalist>
          </div>
        </div>
      </div>

      {/* Query preview */}
      {canExport && (
        <Card>
          <SectionTitle>EXPORT QUERY</SectionTitle>
          <div style={{ ...mono, fontSize: "11px", color: "var(--color-text)", lineHeight: 1.9 }}>
            Factory: <span style={{ color: "var(--color-accent2)" }}>{form.factory}</span><br />
            Buyer: <span style={{ color: "var(--color-accent2)" }}>{form.client}</span><br />
            Period: <span style={{ color: "var(--color-accent2)" }}>{form.date_from} → {form.date_to}</span>
            {form.style && <><br />Style: <span style={{ color: "var(--color-accent2)" }}>{form.style}</span></>}
            {form.po    && <><br />PO: <span style={{ color: "var(--color-accent2)" }}>{form.po}</span></>}
          </div>
        </Card>
      )}

      <PrimaryBtn onClick={handleExport} disabled={!canExport || exporting}>
        {exporting ? "GENERATING…" : "⬇  DOWNLOAD EXCEL SUMMARY"}
      </PrimaryBtn>
    </div>
  );
}

export default ExportView;