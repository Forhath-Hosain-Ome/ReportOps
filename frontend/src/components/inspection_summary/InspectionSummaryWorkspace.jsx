import { useState } from "react";
import { Card } from "../../primitives/Card";
import ReportBlocksPreview, { Metrics, TopDefects } from "./ReportBlocksPreview";

import { shown, percent, hundredFormat } from "./format";

const sections = [["overview", "Overview"], ["dashboard", "QC Dashboard"], ["analysis", "Analysis"], ["summary", "Summary"], ["detail", "100% Detail"]];

function OverviewPanel({ report }) {
  const r = report.reconciliation;
  const sources = report.sources;
  return <section aria-label="Overview"><h2>Overview</h2><div className="inspection-stack">
    <Card><h3>Report readiness</h3><p>Generation: {report.overview.generation_status} · Download: {report.job.download_ready ? "Ready" : "Unavailable"}</p>
      <p>Expires: {new Date(report.job.expires_at).toLocaleString()}</p><p>Report sections: {report.overview.sections.join(" · ")}</p>
      <p>Inspection Summary: {sources.inspection_summary ? "Present" : "Not supplied"} · 100% Data: {sources.hundred_percent ? "Present" : "Not supplied"}</p>
      {sources.hundred_percent && <p>100% Format: {hundredFormat(sources.hundred_percent_format)}</p>}
      {!report.available_sections.qc_dashboard && <p>QC Dashboard unavailable: {sources.hundred_percent ? "Final source missing" : "100% source missing"}.</p>}
      <h4>Source blocks in report order</h4><ol>{report.overview.blocks.map((b) => <li key={b.id}>{b.name}{b.empty ? " — no inspection records" : ""}</li>)}</ol>
    </Card>
    <Card><h3>Inspection coverage</h3><div className="inspection-grid">{report.analysis.map((b) => <div key={b.id}>
      <h4>{b.title}</h4><p>{shown(b.date_start)} to {shown(b.date_end)}</p><p>{shown(b.inspection_days)} Days · {shown(b.count)} {b.count_kind === "style" ? "Styles" : "Audits"}</p></div>)}</div></Card>
    {report.available_sections.detail_100 && <Card><h3>Validation & reconciliation</h3><p>Reconciliation: {r.status}</p><p>Defect Categories: {r.defect_category_count} · Defect Fields: {r.defect_field_count}</p>
      <Metrics values={[["Inspection Qty", r.inspection_qty], ["Pass Qty", r.pass_qty], ["Defect Qty", r.defect_qty],
        ["Defect category total", r.defect_category_total], ["Records", r.record_count], ["Inspection days", r.inspection_day_count], ["Styles", r.style_count]]} />
      <ul>{[["Inspection matches detail", r.inspection_matches_detail], ["Pass matches detail", r.pass_matches_detail],
        ["Defects match categories", r.defect_matches_categories], ["Record count valid", r.record_count_valid]].map(([label, ok]) => <li key={label}>{label}: {ok ? "Passed" : "Failed"}</li>)}</ul>
    </Card>}</div></section>;
}

function DashboardTeam({ title, team, raw }) {
  return <Card><h3>{title}</h3><Metrics values={[["Duration days", team.duration_days],
    ...(raw ? [["Style count", team.style_count], ["Passed Qty", team.passed_qty]] : [["Audit count", team.audit_count], ["Shipment Qty", team.shipment_qty]]),
    ["Inspected Qty", team.inspected_qty], ["Defect Qty", team.defect_qty], ["Defect ratio", percent(team.defect_ratio)]]} />
    <TopDefects groups={team.top_defects} label={`${title} Top 5 comparison`} /></Card>;
}

function QcDashboardPreview({ dashboard }) {
  const d = dashboard;
  return <section aria-label="QC Dashboard"><h2>QC Dashboard</h2>
    {!d.matched_style_count && <div className="inspection-notice"><h3>No exact style matches were found between Final and 100%.</h3>
      <p>Comparison uses only the exact style intersection, with surrounding whitespace trimmed. Full source totals remain available in Analysis, Summary and 100% Detail.</p></div>}
    {!d.final_available && <p>Final report not provided.</p>}
    <div className="inspection-grid inspection-comparison">
      <DashboardTeam title="100% team" team={d.team_100} raw />
      <Card><h3>Comparison</h3><p>Matched styles: {d.matched_style_count}</p>
        {d.matched_styles.length > 0 && <ul>{d.matched_styles.map((style) => <li key={style}>{style}</li>)}</ul>}
        <p>Ratio reduction: {percent(d.comparison.ratio_reduction)}</p><p>Inspection factor: {shown(d.comparison.inspection_factor)}</p>
        <p>Equivalent findings: {shown(d.comparison.equivalent_findings)}</p>{d.comparison.equivalent_calculation && <p>{d.comparison.equivalent_calculation}</p>}
      </Card>
      <DashboardTeam title="Final team" team={d.final} />
    </div></section>;
}

function RawDetailPreview({ detail }) {
  return <section aria-label="100% Detail"><h2>100% Detail</h2><p>{detail.record_count} source records · {detail.columns.length} fields. Scroll inside the table to view every field.</p>
    <div className="inspection-table-scroll inspection-detail" tabIndex={0} role="region" aria-label="Scrollable 100% detail">
      <table><caption>100% inspection detail, weekly subtotals and grand total</caption><thead><tr>{detail.columns.map((c) => <th key={c.key} scope="col">
        <span className="inspection-column-group">{c.group || "Inspection"}{c.number ? ` · ${c.number}` : ""}</span>{c.label}</th>)}</tr></thead>
        <tbody>{detail.rows.map((row, i) => <tr key={i} className={`inspection-row-${row.kind}`} data-kind={row.kind}>
          {detail.columns.map((c, j) => j === 0 ? <th scope="row" key={c.key}>{shown(row.values[c.key])}</th> : <td key={c.key}>{shown(row.values[c.key])}</td>)}</tr>)}</tbody></table>
    </div></section>;
}

export default function InspectionSummaryWorkspace({ report }) {
  const [section, setSection] = useState("overview");
  return <div className="inspection-stack"><nav aria-label="Report sections" className="inspection-section-nav">
    {sections.filter(([id]) => id === "overview" || report.available_sections[({dashboard:"qc_dashboard",detail:"detail_100"})[id] || id]).map(([id, label]) => <button key={id} aria-current={section === id ? "page" : undefined} aria-controls="inspection-section"
      onClick={() => setSection(id)}>{label}</button>)}</nav>
    <div id="inspection-section">
      {section === "overview" && <OverviewPanel report={report} />}
      {section === "dashboard" && report.available_sections.qc_dashboard && <QcDashboardPreview dashboard={report.dashboard} />}
      {["analysis", "summary"].includes(section) && <ReportBlocksPreview blocks={report[section]} mode={section} />}
      {section === "detail" && report.available_sections.detail_100 && <RawDetailPreview detail={report.detail} />}
    </div></div>;
}
