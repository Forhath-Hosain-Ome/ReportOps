import { useRef, useState } from "react";

export default function InspectionSummaryForm({ active, uploading, onGenerate }) {
  const [inspectionSummary, setInspectionSummary] = useState(null);
  const [raw, setRaw] = useState(null);
  const [errors, setErrors] = useState([]);
  const submitted = useRef(false);
  function submit(event) {
    event.preventDefault();
    if (active || submitted.current) return;
    const messages = [];
    if (!inspectionSummary && !raw) messages.push("At least one Inspection Summary or 100% workbook is required.");
    for (const [name, file] of [["Inspection Summary", inspectionSummary], ["100% Inspection Data", raw]]) {
      if (file && (!file.name.toLowerCase().endsWith(".xlsx") || !file.size || file.size > 50 * 1024 * 1024)) {
        messages.push(`${name}: choose a nonempty .xlsx workbook, at most 50 MB.`);
      }
    }
    setErrors(messages);
    if (messages.length) return;
    submitted.current = true;
    onGenerate(inspectionSummary, raw);
    // The page owns the persistent upload lock; this closes same-event repeats.
    queueMicrotask(() => { submitted.current = false; });
  }
  return <section className="inspection-card" aria-label="Generate inspection report">
    <form onSubmit={submit} aria-busy={active}>
      <fieldset disabled={active}>
        <legend>Choose one or both source workbooks</legend>
        <div className="inspection-grid">
          <label className="inspection-file">Inspection Summary
            <input aria-label="Inspection Summary" type="file" accept=".xlsx" onChange={(event) => setInspectionSummary(event.target.files?.[0] || null)} /><span className="inspection-muted">Optional</span></label>
          <label className="inspection-file">100% Inspection Data
            <input aria-label="100% Inspection Data" type="file" accept=".xlsx" onChange={(event) => setRaw(event.target.files?.[0] || null)} /><span className="inspection-muted">Optional</span></label>
        </div>
        <p>Supports Raw or structured 100% workbook formats. At least one workbook is required.</p>
        <button type="submit" disabled={active}>{uploading ? "Uploading…" : "Generate Report"}</button>
      </fieldset>
    </form>
    {errors.length > 0 && <div role="alert" className="inspection-error"><ul>{errors.map((m) => <li key={m}>{m}</li>)}</ul></div>}
  </section>;
}
