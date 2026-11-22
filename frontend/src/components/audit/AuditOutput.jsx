/**
 * AuditOutput.jsx
 * ----------------
 * Rendered by OutputPanel when output.source === "audit".
 *
 * Handles these output.type values:
 *   audit-upload          → UploadView
 *   audit-batch-list      → AuditBatchList
 *   audit-batch           → AuditBatchDetail
 *   audit-batch-logs      → AuditBatchLogsView
 *   audit-export          → ExportView
 *   audit-retry-search    → RetrySearchView
 *   audit-retry-upload    → RetryUploadView
 *   audit-settings        → SettingsView (buyers / factories / pairs)
 */

import { useOutputStore } from "../../store/outputStore";
import { saveBlob } from "../../constants";
import AuditBatchDetail from "../../views/BatchDetailView";
import AuditBatchLogsView from "../../views/BatchLogsView";
import AuditBatchList from "../../views/BatchListView";
import ExportView from "../../views/ExportView";
import RetrySearchView from "../../views/RetrySearchView";
import RetryUploadView from "../../views/RetryUploadView";
import SettingsView from "../../views/SettingsView";
import UploadView from "../../views/UploadView";
import {
  fetchBatch,
  downloadErrorJson,
} from "../../services/finalSummaryApi";

// ─────────────────────────────────────────────────────────────────────────────
// Router — dispatches to the right view based on output.type
// ─────────────────────────────────────────────────────────────────────────────
export default function AuditOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();

  // Shared action handler used by batch lists
  const handleAction = async (action, id, meta = {}) => {
    switch (action) {
      case "view": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("audit-batch", data, `Batch #${id}`, { source: "audit" });
          addLog({ level: "info", message: `Loaded Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Batch #${id}`, error: e?.message || e });
          setLoading(false);
        }
        break;
      }
      case "logs": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("audit-batch-logs", data, `Logs · Batch #${id}`, { source: "audit" });
          addLog({ level: "info", message: `Logs loaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load logs for Batch #${id}`, error: e?.message || e });
          setLoading(false);
        }
        break;
      }
      case "retry-download": {
        addLog({ level: "info", message: `Downloading error JSON for Batch #${id}…` });
        try {
          const payload = await downloadErrorJson(id);
          const blob    = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
          saveBlob(blob, `batch-${id}-errors.json`);
          addLog({ level: "success", message: `Error JSON downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
      }
      default:
        break;
    }
  };

  switch (output.type) {
    case "audit-upload":
      return <UploadView data={output.data} />;

    case "audit-batch-list":
      return (
        <AuditBatchList
          data={output.data}
          action={output.action}
          onAction={handleAction}
        />
      );

    case "audit-batch":
      return <AuditBatchDetail data={output.data} />;

    case "audit-batch-logs":
      return <AuditBatchLogsView data={output.data} />;

    case "audit-export":
      return <ExportView data={output.data} />;

    case "audit-retry-search":
      return <RetrySearchView />;

    case "audit-retry-upload":
      return <RetryUploadView />;

    case "audit-settings":
      return <SettingsView data={output.data} settingsKey={output.settingsKey} />;

    default:
      return null;
  }
}