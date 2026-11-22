import axios from "axios";
import { attachInterceptors } from "./apiClient";

const puma_api = attachInterceptors(
  axios.create({
    baseURL: "/puma/",
  })
);


// ── Batches ───────────────────────────────────────────────────────────────────
export const fetchBatches = (params) =>
  puma_api.get("batches/", { params }).then((r) => r.data);

export const fetchBatch = (pk) =>
  puma_api.get(`batches/${pk}/`).then((r) => r.data);

export const uploadBatch = (files) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return puma_api.post("batches/upload/", fd).then((r) => r.data);
};

/**
 * Retry failed PDFs for a batch.
 * @param {number} pk - Batch ID
 * @param {string[]} [filenames] - Optional list of specific filenames to retry.
 *   Omit (or pass []) to retry ALL unretried failures.
 */
export const retryBatch = (pk, filenames = []) =>
  puma_api
    .post(`batches/${pk}/retry/`, filenames.length ? { filenames } : {})
    .then((r) => r.data);

export const fetchBatchLogs = (pk) =>
  puma_api.get(`batches/${pk}/logs/`).then((r) => r.data);

export const downloadExcel = (pk) =>
  puma_api.get(`batches/${pk}/excel/`, { responseType: "blob" }).then((r) => r.data);

// ── Reports ───────────────────────────────────────────────────────────────────
export const fetchReports = (params) =>
  puma_api.get("reports/", { params }).then((r) => r.data);

export const fetchReport = (pk) =>
  puma_api.get(`reports/${pk}/`).then((r) => r.data);

export const downloadReportPDF = (pk) =>
  puma_api.get(`reports/${pk}/pdf/`, { responseType: "blob" }).then((r) => r.data);

export const downloadCertificate = (pk) =>
  puma_api.get(`reports/${pk}/certificate/`, { responseType: "blob" }).then((r) => r.data);

export const fetchCertificateLogs = (pk) =>
  puma_api.get(`reports/${pk}/certificates/`).then((r) => r.data);