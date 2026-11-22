import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import InspectionSummaryForm from "../components/inspection_summary/InspectionSummaryForm";
import InspectionSummaryWorkspace from "../components/inspection_summary/InspectionSummaryWorkspace";
import { createJob, downloadResult, errorMessages, getJob, getPreview } from "../services/inspectionSummaryApi";
import { saveBlob } from "../utils/fileUtils";
import "../components/inspection_summary/inspectionSummary.css";

const stages = { VALIDATING: "Validating workbooks", QUEUED: "Queued", DISCOVERING_SHEETS: "Discovering inspection sheets",
  PARSING_SHEETS: "Reading inspection sheets", PARSING_RAW: "Reading 100% data",
  WRITING_RESULT: "Building report", VERIFYING_RESULT: "Verifying report",
  COMPLETED: "Completed", FAILED: "Failed" };

export default function InspectionSummaryPage() {
  const [jobId, setJobId] = useState(null);
  const [expiredJob, setExpiredJob] = useState(null);
  const [errors, setErrors] = useState([]);
  const [downloading, setDownloading] = useState(false);
  const lock = useRef(false);
  const upload = useMutation({ mutationFn: ([summary, raw]) => createJob(summary, raw),
    onSuccess: (job) => { setJobId(job.job_id); setErrors([]); },
    onError: (error) => setErrors(errorMessages(error)),
    onSettled: () => { lock.current = false; } });
  const status = useQuery({ queryKey: ["inspection-summary", jobId], enabled: Boolean(jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
    refetchInterval: (query) => !query.state.error && ["PENDING", "PROCESSING"].includes(query.state.data?.status) ? 2000 : false });
  const job = status.data;
  const expiresAt = job?.expires_at;
  const expired = expiredJob === jobId && jobId !== null || Boolean(expiresAt && new Date(expiresAt).getTime() <= Date.now());
  useEffect(() => {
    if (!expiresAt || !jobId) return;
    const timeout = window.setTimeout(() => setExpiredJob(jobId), Math.min(2147483647, Math.max(0, new Date(expiresAt).getTime() - Date.now())));
    return () => window.clearTimeout(timeout);
  }, [expiresAt, jobId]);
  const preview = useQuery({ queryKey: ["inspection-summary-preview", jobId],
    queryFn: ({ signal }) => getPreview(jobId, signal), enabled: job?.status === "COMPLETED" && !expired,
    retry: false, gcTime: 0, refetchOnWindowFocus: false });
  const active = upload.isPending || Boolean(jobId && !expired && (!job || ["PENDING", "PROCESSING"].includes(job.status)) && !status.error);
  const messages = [...errors, ...(status.error ? errorMessages(status.error) : []),
    ...(job?.error ? [job.error.code, ...[job.error.input, job.error.sheet, job.error.cell].filter(Boolean), job.error.detail].filter(Boolean) : [])];

  function generate(summary, raw) {
    if (lock.current || active) return;
    lock.current = true;
    setJobId(null);
    setErrors([]);
    upload.mutate([summary, raw]);
  }
  async function download() {
    if (downloading || expired) return;
    setDownloading(true);
    try { saveBlob(await downloadResult(jobId)); setErrors([]); }
    catch (error) { setErrors(errorMessages(error)); }
    finally { setDownloading(false); }
  }
  return <div className="inspection-summary">
    <header className="inspection-heading"><div><p className="inspection-eyebrow">REPORT WORKSPACE</p>
      <h1>Inspection Summary</h1><p>Upload one or both source workbooks, review your report, and download Result.xlsx.</p>
      <p className="inspection-muted">Excel is the authoritative report. Downloads and previews expire after 24 hours.</p></div></header>
    <InspectionSummaryForm active={active} uploading={upload.isPending} onGenerate={generate} />
    {messages.length > 0 && <div role="alert" className="inspection-error"><ul>{messages.map((message, i) => <li key={i}>{String(message)}</li>)}</ul></div>}
    {status.error && <button onClick={() => status.refetch()}>Refresh job status</button>}
    {(jobId || upload.isPending) && <section className="inspection-card" aria-label="Job progress">
      <div role="status" aria-live="polite"><h2>{expired ? "Report expired" : upload.isPending ? "Uploading…" : job?.status || "Loading report status…"}</h2>
        {job && <p>{stages[job.stage] || String(job.stage || job.status).replaceAll("_", " ")}</p>}</div>
      {expiresAt && <p>Expires: {new Date(expiresAt).toLocaleString()}</p>}
      {job?.sheet_manifest?.length > 0 && <ol>{job.sheet_manifest.map((sheet, i) => <li key={i}>{sheet.name}{sheet.empty ? " — no inspection records" : ""}</li>)}</ol>}
      {job?.status === "COMPLETED" && <button onClick={download} disabled={downloading || expired || !job.download_ready}>
        {expired ? "Report expired" : downloading ? "Downloading…" : "Download Result.xlsx"}</button>}
    </section>}
    {job?.status === "COMPLETED" && !expired && <section aria-label="Report preview" aria-busy={preview.isFetching}>
      {preview.isPending && <p>Loading report preview…</p>}
      {preview.error && <div role="alert" className="inspection-error"><h2>Preview unavailable</h2>
        <p>The workbook completed. You can still download it when available.</p>
        <ul>{errorMessages(preview.error).map((m, i) => <li key={i}>{m}</li>)}</ul>
        <button onClick={() => preview.refetch()}>Retry preview</button></div>}
      {preview.data && !preview.error && <InspectionSummaryWorkspace key={jobId} report={preview.data} />}
    </section>}
  </div>;
}
