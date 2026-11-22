import axios from "axios";
import { attachInterceptors } from "./apiClient";

const api = attachInterceptors(axios.create({ baseURL: "/" }));

export function createJob(inspectionSummaryFile, rawFile) {
  const body = new FormData();
  if (inspectionSummaryFile) body.append("inspection_summary", inspectionSummaryFile);
  if (rawFile) body.append("hundred_percent", rawFile);
  return api.post("inspection-summary/jobs/", body).then((response) => response.data);
}

export function getJob(jobId, signal) {
  return api.get(`inspection-summary/jobs/${jobId}/`, { signal }).then((response) => response.data);
}

export function getPreview(jobId, signal) {
  return api.get(`inspection-summary/jobs/${jobId}/preview/`, { signal }).then((response) => response.data);
}

export async function downloadResult(jobId) {
  try {
    const response = await api.get(`inspection-summary/jobs/${jobId}/download/`, { responseType: "blob" });
    return { blob: response.data, filename: "Result.xlsx", contentType: response.headers["content-type"] };
  } catch (error) {
    if (error.response?.data instanceof Blob) {
      try { error.response.data = JSON.parse(await error.response.data.text()); } catch { /* Keep the HTTP error. */ }
    }
    throw error;
  }
}

export function errorMessages(error) {
  const details = error?.response?.data || error;
  const flatten = (value, prefix = "") => {
    if (value == null) return [];
    if (typeof value === "string") return [prefix ? `${prefix}: ${value}` : value];
    if (Array.isArray(value)) return value.flatMap((item) => flatten(item, prefix));
    if (typeof value === "object") return Object.entries(value).flatMap(([key, item]) => flatten(item, prefix ? `${prefix}.${key}` : key));
    return [String(value)];
  };
  return error?.message && !error.response ? [error.message] : flatten(details);
}
