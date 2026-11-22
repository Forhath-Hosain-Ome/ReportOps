/**
 * MailFetchPage.jsx
 *
 * Follows the exact same shell as AuditSummaryPage / Top5Page:
 *   DashboardLayout → TopNav | LogsPanel | ApiMenu | OutputPanel
 *
 * ApiMenu sections (MAIL_FETCH_SECTIONS in apiGroup.js):
 *   ACCOUNTS  → list the 3 shared company mailboxes
 *   SEARCH    → start a search job, track progress via WebSocket
 *   DOWNLOADS → single attachment or selected-as-zip
 *   HISTORY   → this user's download audit log
 *
 * OAuth (admin-only) is intentionally NOT handled here -- it's a
 * browser redirect to Google's consent screen, not a UI interaction
 * that fits the normal OutputPanel flow. An admin would hit that URL
 * directly from Django admin or a one-off setup page.
 *
 * Search flow (mirrors Top5Page's job pattern):
 *   1. User selects "Start Search" → form renders in OutputPanel
 *   2. User submits → POST /mail-fetch/search/ → SearchJob row created
 *   3. Page opens WebSocket on job.id → streams progress into logs
 *   4. On "complete" event → results (attachment list) set into output
 *   5. User selects attachments → "Download Selected as ZIP" triggers
 */

import { useRef } from "react";
import { useOutputStore } from "../store/outputStore";
import { useAuthStore }   from "../store/authStore";
import DashboardLayout    from "../components/layout/DashboardLayout";
import {
  fetchAccounts,
  startSearch,
  fetchSearchJob,
  openSearchJobSocket,
  downloadAttachment,
  downloadAttachmentsAsZip,
  fetchDownloadHistory,
} from "../services/mailFetchApi";


export default function MailFetchPage() {
  const { user }                                    = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();

  // Keep a ref to the active WebSocket so we can close it if the user
  // navigates away or starts a new search before the current one finishes.
  const socketRef = useRef(null);

  const _closeSocket = () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  };

  const handleSelect = async (ep) => {
    switch (ep.id) {

      // ── Accounts ────────────────────────────────────────────────────────
      case "mailfetch-accounts-list": {
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: "Loading mailboxes…" });
        try {
          const data = await fetchAccounts();
          const list = Array.isArray(data?.results) ? data.results
                     : Array.isArray(data)           ? data
                     : [];
          setOutput(
            "mailfetch-accounts-list",
            list,
            "Mailboxes",
            { source: "mailfetch" }
          );
          addLog({ level: "success", message: `${list.length} mailbox(es) loaded` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Start Search — render a form in OutputPanel ──────────────────
      case "mailfetch-search-start": {
        _closeSocket();
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: "Loading mailboxes for search form…" });
        try {
          const data     = await fetchAccounts();
          const accounts = Array.isArray(data?.results) ? data.results
                         : Array.isArray(data)           ? data
                         : [];
          setOutput(
            "mailfetch-search-start",
            { accounts },
            "Search Gmail",
            { source: "mailfetch" }
          );
          addLog({ level: "success", message: "Search form ready" });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load accounts: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Search Job detail — retrieve a previously-run job ────────────
      case "mailfetch-search-job": {
        // Show the list of recent search jobs so the user can pick one.
        // There's no dedicated "list search jobs" endpoint yet, but
        // SearchJobViewSet supports list -- wire it when you add that
        // endpoint, or show a job-id input form here for now.
        clearOutput();
        setOutput(
          "mailfetch-search-job-pick",
          {},
          "Retrieve Search Job",
          { source: "mailfetch" }
        );
        break;
      }

      // ── Download single attachment ────────────────────────────────────
      // Note: this case is triggered programmatically from OutputPanel
      // when the user clicks a single attachment row in the results
      // list -- not directly from the ApiMenu (the menu entry exists
      // for documentation purposes in the API explorer). The OutputPanel
      // component calls onAction({ id: "mailfetch-download-single", ...params })
      // with the attachment params already filled in.
      case "mailfetch-download-single": {
        const { account_id, message_id, attachment_id, filename } = ep;
        addLog({ level: "info", message: `Downloading ${filename}…` });
        try {
          await downloadAttachment({ account_id, message_id, attachment_id, filename });
          addLog({ level: "success", message: `${filename} downloaded` });
        } catch (e) {
          addLog({ level: "error", message: `Download failed: ${e.message}` });
        }
        break;
      }

      // ── Download selected as ZIP ─────────────────────────────────────
      // Same as above -- triggered from OutputPanel's "Download ZIP"
      // button once the user has selected attachments from search results.
      case "mailfetch-download-zip": {
        const { account_id, attachments } = ep;
        if (!attachments?.length) {
          addLog({ level: "warn", message: "No attachments selected" });
          break;
        }
        addLog({ level: "info", message: `Zipping ${attachments.length} attachment(s)…` });
        try {
          await downloadAttachmentsAsZip(account_id, attachments);
          addLog({ level: "success", message: `ZIP of ${attachments.length} file(s) downloaded` });
        } catch (e) {
          addLog({ level: "error", message: `ZIP download failed: ${e.message}` });
        }
        break;
      }

      // ── History ──────────────────────────────────────────────────────
      case "mailfetch-history-list": {
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: "Loading download history…" });
        try {
          const data = await fetchDownloadHistory();
          const list = Array.isArray(data?.results) ? data.results
                     : Array.isArray(data)           ? data
                     : [];
          setOutput(
            "mailfetch-history-list",
            list,
            "Download History",
            { source: "mailfetch" }
          );
          addLog({ level: "success", message: `${list.length} record(s)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      default:
        break;
    }
  };

  /**
   * Called by the OutputPanel's search form when the user submits.
   * Separated from handleSelect because it needs to carry form data
   * (account_id, subject, report_date, attachment_contains) that the
   * ApiMenu endpoint object doesn't carry -- same pattern you'd use
   * in AuditSummaryPage for the upload form submission.
   *
   * @param {{ account_id: number, subject: string, report_date: string, attachment_contains: string }} formData
   */
  const handleSearchSubmit = async (formData) => {
    _closeSocket();
    clearOutput();
    setLoading(true);
    addLog({ level: "info", message: "Starting search…" });

    let job;
    try {
      job = await startSearch(formData);
      addLog({ level: "info", message: `Search job #${job.id} created — connecting…` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to start search: ${e.message}` });
      setLoading(false);
      return;
    }

    // Set an initial "pending" output so the OutputPanel shows a progress
    // state while the WebSocket streams in results.
    setOutput(
      "mailfetch-search-progress",
      { job, attachments: [] },
      "Searching Gmail…",
      { source: "mailfetch" }
    );

    socketRef.current = openSearchJobSocket(job.id, {
      onProgress: ({ stage, progress_percent }) => {
        addLog({ level: "info", message: `${stage || "Scanning…"} (${progress_percent ?? 0}%)` });
      },
      onComplete: ({ result }) => {
        addLog({ level: "success", message: `Found ${result?.length ?? 0} attachment(s)` });
        setOutput(
          "mailfetch-search-results",
          { job, attachments: result ?? [], account_id: formData.account_id },
          `Results — ${result?.length ?? 0} attachment(s)`,
          { source: "mailfetch" }
        );
        socketRef.current = null;
      },
      onError: ({ error }) => {
        addLog({ level: "error", message: `Search failed: ${error}` });
        setLoading(false);
        socketRef.current = null;
      },
      onSocketError: (err) => {
        addLog({ level: "error", message: `WebSocket error: ${err?.message ?? "unknown"}` });
        setLoading(false);
        socketRef.current = null;
      },
    });
  };

  return (
    <DashboardLayout
      onSelect={handleSelect}
      // Pass handleSearchSubmit down so OutputPanel's search form can
      // call it on submit. How you thread this through OutputPanel depends
      // on your existing OutputPanel/AuditOutput prop conventions -- if
      // OutputPanel already has an onSubmit/onAction prop used by other
      // pages, use the same one here rather than adding a new prop.
      onSubmit={handleSearchSubmit}
    />
  );
}