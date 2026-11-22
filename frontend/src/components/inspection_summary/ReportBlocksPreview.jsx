import { Card } from "../../primitives/Card";

import { shown, percent } from "./format";

export function Metrics({ values }) {
  return <dl className="inspection-grid inspection-metrics">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{shown(value)}</dd></div>)}</dl>;
}

export function TopDefects({ groups, label }) {
  if (!groups.length) return <p>No positive defect ranks available.</p>;
  return <div className="inspection-table-scroll" tabIndex={0} role="region" aria-label={label}>
    <table><caption>{label}</caption><thead><tr><th scope="col">Rank</th><th scope="col">Defects / category</th>
      <th scope="col">Quantity</th><th scope="col">Ratio</th></tr></thead><tbody>{groups.map((group) => <tr key={group.rank}>
        <th scope="row">{group.rank}</th><td>{group.defects.map((d, i) => <div key={i}>{d.label}{d.category ? ` · ${d.category}` : ""}</div>)}</td>
        <td>{shown(group.quantity)}</td><td>{percent(group.ratio)}</td></tr>)}</tbody></table>
  </div>;
}

function ManpowerPanel({ manpower }) {
  return <section aria-label="MANPOWER"><h4>MANPOWER</h4><p>{shown(manpower.days)} days · Aggregate persons: {shown(manpower.aggregate_persons)}</p>
    <p className="inspection-muted">Date-linked source values. No aggregate is inferred.</p>
    <dl className="inspection-manpower">{manpower.entries.map((entry) => <div key={entry.date}>
      <dt>{entry.date}</dt><dd>{entry.values.map((v) => v == null ? "Not provided" : String(v)).join(" / ")}</dd></div>)}</dl>
  </section>;
}

export default function ReportBlocksPreview({ blocks, mode }) {
  return <section aria-label={mode === "analysis" ? "Analysis" : "Summary"}>
    <h2>{mode === "analysis" ? "Analysis" : "Summary"}</h2>
    <p>{mode === "analysis" ? "Top defect ratio based on inspected quantity" : "Top defect ratio based on total defect quantity"}</p>
    <div className="inspection-stack">{blocks.map((block) => <Card key={block.id}>
      <h3>{block.title}</h3><p>{block.factory_names.join(", ") || "Factory not provided"}</p>
      <p>{shown(block.date_start)} to {shown(block.date_end)} · {shown(block.inspection_days)} Days · {block.count == null ? "—" : String(block.count).padStart(2, "0")}-{block.count_kind === "style" ? "Style" : "Audit"}</p>
      <Metrics values={[...(block.kind === "raw" ? [["Pass Qty", block.pass_qty]] : [["Shipment Qty", block.shipment_qty]]),
        ["Inspected Qty", block.inspected_qty], ["Defect Qty", block.defect_qty], ["Defect ratio", percent(block.defect_ratio)]]} />
      <p>Items: {block.items.join(", ") || "—"} · Team leader: {shown(block.team_leader)}</p>
      {block.empty ? <p>No inspection records found for this section.</p> : <TopDefects groups={block.top_defects} label={`${block.title} Top 5 defects`} />}
      {mode === "analysis" && block.kind === "raw" && block.manpower && <ManpowerPanel manpower={block.manpower} />}
    </Card>)}</div>
  </section>;
}
