import axios from "axios";
import { attachInterceptors } from "./apiClient";

const image_api = attachInterceptors(
  axios.create({
    baseURL: "/",
  })
);

const normalizeReport = (report) => ({
  ...report,
  style: report.style || report.folder_name || report.report_number || "",
});

const normalizeReportPayload = (payload) => {
  if (payload == null) return payload;
  if (Array.isArray(payload)) return payload.map(normalizeReport);
  if (Array.isArray(payload.results)) {
    return {
      ...payload,
      results: payload.results.map(normalizeReport),
    };
  }
  return normalizeReport(payload);
};

const normalizeBatch = (batch) => ({
  ...batch,
  reports: batch.reports?.map(normalizeReport) || batch.reports,
});

// ── Shared download helper ────────────────────────────────────────────────────
export const fetchBatches = (params) =>
  image_api.get("image/folder/batches/", { params }).then((r) => r.data);

export const fetchBatch = (pk) =>
  image_api.get(`image/folder/batches/${pk}/`).then((r) => normalizeBatch(r.data));

export const uploadBatch = (files, paths = [], date = null, style = "", isRenamedFile = false) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  paths.forEach((path) => fd.append("paths", path));
  if (date) fd.append("date", date);
  if (style) fd.append("style", style);
  if (isRenamedFile) fd.append("is_renamed_file", "true");
  return image_api.post("image/folder/upload/", fd).then((r) => r.data);
};

export const fetchBatchLogs = (pk, params) =>
  image_api.get(`image/folder/batches/${pk}/logs/`, { params }).then((r) => r.data);

// ── Reports ───────────────────────────────────────────────────────────────────
export const fetchReports = (params) =>
  image_api.get("image/folder/reports/", { params }).then((r) => normalizeReportPayload(r.data));

export const fetchReport = (pk) =>
  image_api.get(`image/folder/reports/${pk}/`).then((r) => normalizeReport(r.data));

const responseFilename = (disposition, fallback) => {
  const encoded = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (encoded) {
    try { return decodeURIComponent(encoded[1].trim()); } catch { /* Use the plain filename below. */ }
  }
  return disposition.match(/filename\s*=\s*"([^"]+)"/i)?.[1]
    || disposition.match(/filename\s*=\s*([^;]+)/i)?.[1]?.trim()
    || fallback;
};

const download = (pk, extension) => image_api
  .get(`image/folder/reports/${pk}/${extension}/`, { responseType: "blob" })
  .then((r) => ({
    blob: r.data,
    filename: responseFilename(r.headers["content-disposition"] || "", `report-${pk}.${extension}`),
    contentType: r.headers["content-type"],
  }));

export const downloadReportPDF = (pk) => download(pk, "pdf");
export const downloadReportDOCX = (pk) => download(pk, "docx");
export const retryBatch = (pk, reportIds) => image_api.post(`image/folder/batches/${pk}/retry/`,
  reportIds ? { report_ids: reportIds } : {}).then((r) => r.data);
export const fetchSettings = () => image_api.get("image/settings/").then((r) => r.data);
export const updateSettings = (data) => image_api.patch("image/settings/", data).then((r) => r.data);
