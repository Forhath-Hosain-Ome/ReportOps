import axios from "axios";
import { attachInterceptors } from "./apiClient";

const mail_download_api = attachInterceptors(
  axios.create({
    baseURL: "/mail-fetch/",
  })
);

// ── Accounts (3 shared company mailboxes) ──────────────────────────────────
export const fetchAccounts = () =>
  mail_download_api.get("accounts/").then((r) => r.data);

// ── OAuth (admin-only) ──────────────────────────────────────────────────────
export const mailFetchOAuthStartUrl = () => "/mail-fetch/oauth/start/";

// ── Search ──────────────────────────────────────────────────────────────────
/**
 * Kicks off a search job. Returns the SearchJob record immediately
 * (status: "pending"), including its `id`. Open the WebSocket using that
 * id -- see openSearchJobSocket below. This matches the same job-record
 * pattern your project already uses for top5/puma jobs, not a one-off
 * group_name string.
 *
 * @param {{ account_id: number, subject?: string, report_date?: string, attachment_contains?: string }} params
 */
export const startSearch = (params) =>
  mail_download_api.post("search/", params).then((r) => r.data);

export const fetchSearchJob = (jobId) =>
  mail_download_api.get(`search/${jobId}/`).then((r) => r.data);

/**
 * Opens a WebSocket for a SearchJob's progress, matching the existing
 * jobs/{pk}/progress/ convention used elsewhere in the project.
 * On connect, the server immediately sends a snapshot (current status),
 * so this works correctly even if called after the job already
 * completed -- you'll get an immediate "complete" event instead of
 * waiting forever.
 *
 * @param {number} jobId
 * @param {{ onProgress?: (data: object) => void, onComplete?: (data: object) => void, onError?: (data: object) => void, onSocketError?: (err: any) => void }} handlers
 * @returns {WebSocket}
 */
export const openSearchJobSocket = (jobId, { onProgress, onComplete, onError, onSocketError } = {}) => {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/mail-fetch/jobs/${jobId}/progress/`);

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event === "complete") {
      onComplete?.(data);
    } else if (data.event === "error") {
      onError?.(data);
    } else {
      onProgress?.(data);
    }
  };

  socket.onerror = (err) => onSocketError?.(err);
  socket.onclose = (event) => {
    if (event.code === 4401) onSocketError?.(new Error("Not authenticated"));
    if (event.code === 4404) onSocketError?.(new Error("Search job not found"));
  };

  return socket;
};

// ── Downloads (synchronous, stream straight to the browser) ───────────────
export const downloadAttachment = (params) =>
  mail_download_api
    .get("download/", { params, responseType: "blob" })
    .then((r) => _triggerBrowserDownload(r.data, params.filename));

export const downloadAttachmentsAsZip = (accountId, attachments) =>
  mail_download_api
    .post("download-zip/", { account_id: accountId, attachments }, { responseType: "blob" })
    .then((r) => _triggerBrowserDownload(r.data, "attachments.zip"));

function _triggerBrowserDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

// ── History ─────────────────────────────────────────────────────────────────
export const fetchDownloadHistory = (params) =>
  mail_download_api.get("history/", { params }).then((r) => r.data);
