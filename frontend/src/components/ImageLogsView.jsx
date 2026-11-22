import { useState } from "react";
import { fetchBatchLogs } from "../services/defectImageApi";

export default function ImageLogsView({ data, batchId }) {
  const [page, setPage] = useState(data);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changePage = async (url) => {
    setBusy(true);
    try {
      setPage(await fetchBatchLogs(batchId, { page: new URL(url, window.location.origin).searchParams.get("page") || 1 }));
      setError("");
    } catch (e) { setError(e.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  };
  return <section>
    <h2>Batch #{batchId} · Processing history</h2>
    <p>{page.status} · {page.count} attempts · {page.last_error_code}</p>
    {error && <p role="alert">{error}</p>}
    {page.results?.map((attempt) => <article key={attempt.id} style={{ padding: 12, marginBottom: 8, border: "1px solid var(--color-border)" }}>
      <strong>{attempt.folder_name} · Attempt generation {attempt.generation} · {attempt.status}</strong>
      <p>{attempt.stage} {attempt.error_code} {attempt.reason}</p>
      {attempt.outcomes?.map((image) => <p key={image.id}>{image.original_filename}: {image.status} {image.failure_reason}</p>)}
    </article>)}
    <button disabled={busy || !page.previous} onClick={() => changePage(page.previous)}>Previous</button>
    <button disabled={busy || !page.next} onClick={() => changePage(page.next)}>Next</button>
  </section>;
}
