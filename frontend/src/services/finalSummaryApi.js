/**
 * -------------------
 * All API calls for the Audit Summary feature.
 *
 * Base URL prefix is handled by final_summary_api (axios instance).
 * That instance should point to  /api/final-summary/
 */

import axios from "axios";
import { attachInterceptors } from "./apiClient";

const final_summary_api = attachInterceptors(
  axios.create({
    baseURL: "/final-summary/",
  })
);

// ─────────────────────────────────────────────────────────────────────────────
// Registration — Buyers
// ─────────────────────────────────────────────────────────────────────────────

/** GET /buyers/ */
export const fetchBuyers = (params) =>
  final_summary_api.get("buyers/", { params }).then((r) => r.data);

/** POST /buyers/ */
export const createBuyer = (payload) =>
  final_summary_api.post("buyers/", payload).then((r) => r.data);

/** PUT /buyers/<pk>/ */
export const updateBuyer = (pk, payload) =>
  final_summary_api.put(`buyers/${pk}/`, payload).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────────
// Registration — Factories
// ─────────────────────────────────────────────────────────────────────────────

/** GET /factories/?buyer=<id> */
export const fetchFactories = (params) =>
  final_summary_api.get("factories/", { params }).then((r) => r.data);

/** POST /factories/ */
export const createFactory = (payload) =>
  final_summary_api.post("factories/", payload).then((r) => r.data);

/** PUT /factories/<pk>/ */
export const updateFactory = (pk, payload) =>
  final_summary_api.put(`factories/${pk}/`, payload).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────────
// Registration — Buyer–Factory Pairs
// ─────────────────────────────────────────────────────────────────────────────

/** GET /pairs/ */
export const fetchPairs = (params) =>
  final_summary_api.get("pairs/", { params }).then((r) => r.data);

/** POST /pairs/ */
export const createPair = (payload) =>
  final_summary_api.post("pairs/", payload).then((r) => r.data);

/** PUT /pairs/<pk>/ */
export const updatePair = (pk, payload) =>
  final_summary_api.put(`pairs/${pk}/`, payload).then((r) => r.data);

/**
 * GET /pairs/options/
 * Returns { buyers, factories, pairs, report_types, report_choices }
 * Used to populate the upload form dropdown.
 */
export const fetchPairOptions = () =>
  final_summary_api.get("pairs/options/").then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────────
// Upload
// ─────────────────────────────────────────────────────────────────────────────

/**
 * POST /upload/
 * @param {File[]}  files           — one or more .xlsx / .xls files
 * @param {number}  pairId          — BuyerFactoryPair.pk
 * @param {string}  inspectionDate  — YYYY-MM-DD
 * Returns { batch_id, pair, buyer, factory, report_type,
 *           inspection_date, total_files, files, ws_channel, message }
 */
export const uploadBatch = (files, pairId, inspectionDate) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("pair_id", pairId);
  fd.append("inspection_date", inspectionDate);
  return final_summary_api.post("upload/", fd).then((r) => r.data);
};

// ─────────────────────────────────────────────────────────────────────────────
// Batches
// ─────────────────────────────────────────────────────────────────────────────

/** GET /batches/?buyer=&factory=&status= */
export const fetchBatches = (params) =>
  final_summary_api.get("batches/", { params }).then((r) => r.data);

/** GET /batches/<pk>/ */
export const fetchBatch = (pk) =>
  final_summary_api.get(`batches/${pk}/`).then((r) => r.data);

/** GET /batches/<pk>/ - alias for fetchBatch */
export const fetchBatchDetail = (pk) =>
  final_summary_api.get(`batches/${pk}/`).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────────
// Retry
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /retry/search/?date=&style=&limit=
 * Returns { count, filters, records: [...] }
 */
export const searchBlocked = (params) =>
  final_summary_api.get("retry/search/", { params }).then((r) => r.data);

/**
 * GET /retry/<pk>/download/
 * Returns the error JSON payload for a batch (blocked records only).
 */
export const downloadErrorJson = (pk) =>
  final_summary_api.get(`retry/${pk}/download/`).then((r) => r.data);

/**
 * POST /retry/upload/
 * Body: multipart — batch_id (int), file (JSON file)
 * Returns { batch_id, submitted, saved, still_blocked: [...] }
 */
export const uploadFixedJson = (batchId, jsonFile) => {
  const fd = new FormData();
  fd.append("batch_id", batchId);
  fd.append("file", jsonFile);
  return final_summary_api.post("retry/upload/", fd).then((r) => r.data);
};

// ─────────────────────────────────────────────────────────────────────────────
// Export
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /export/?factory=&client=&date_from=&date_to=&style=&po=
 * Returns .xlsx blob
 */
export const downloadSummary = (params) =>
  final_summary_api
    .get("export/", { params, responseType: "blob" })
    .then((r) => ({ blob: r.data, headers: r.headers }));

/**
 * GET /options/
 * Returns { factories, clients, styles, po_numbers, min_date, max_date }
 */
export const fetchFilterOptions = () =>
  final_summary_api.get("options/").then((r) => r.data);