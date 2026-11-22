/**
 * ---------------------
 * Replaces FinalSummaryPage.jsx.
 * Follows the same shell as PumaPage / DefectImagePage:
 *   TopNav | LogsPanel | ApiMenu | OutputPanel
 *
 * ApiMenu sections:
 *   UPLOAD   → upload/
 *   BATCHES  → batches/ list, batch detail, batch logs
 *   EXPORT   → export/
 *   RETRY    → retry/search/, retry/<pk>/download/, retry/upload/
 *   SETTINGS → buyers/, factories/, pairs/  (registration)
 *
 * All stage content is rendered via OutputPanel → AuditOutput (new component).
 */
import { useOutputStore } from "../store/outputStore";
import { useAuthStore }   from "../store/authStore";
import DashboardLayout from "../components/layout/DashboardLayout";
import {
  fetchBatches,
  fetchPairOptions,
  fetchFilterOptions,
  fetchBuyers,
  fetchFactories,
  fetchPairs,
} from "../services/finalSummaryApi";


// ── Page ──────────────────────────────────────────────────────────────────────
export default function AuditSummaryPage() {
  const { user }                          = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();

  const handleSelect = async (ep) => {

    switch (ep.id) {

      // ── Upload ──────────────────────────────────────────────────────────
      case "audit-upload": {
        clearOutput();
        // Fetch pair options so the upload form can show a dropdown
        setLoading(true);
        addLog({ level: "info", message: "Loading pair options…" });
        try {
          const options = await fetchPairOptions();
          setOutput(
            "audit-upload",
            { options },
            "Upload Excel Files",
            { source: "audit" }
          );
          addLog({ level: "success", message: `${options.pairs.length} active pair(s) loaded` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load options: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Batch list ──────────────────────────────────────────────────────
      case "audit-batch-list": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches…" });
        try {
          const data = await fetchBatches();
          // Non-staff: filter to own batches on the client side
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          setOutput("audit-batch-list", list, "All Batches", { source: "audit" });
          addLog({ level: "success", message: `Loaded ${list.length} batch(es)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Batch detail / logs — show list first so user picks one ────────
      case "audit-batch-detail":
      case "audit-batch-logs": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches…" });
        try {
          const data = await fetchBatches();
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          setOutput(
            "audit-batch-list",
            list,
            `Batches — ${ep.label}`,
            { source: "audit", action: ep.action }
          );
          addLog({ level: "success", message: `Loaded ${list.length} batch(es)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Export ──────────────────────────────────────────────────────────
      case "audit-export": {
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: "Loading filter options…" });
        try {
          const opts = await fetchFilterOptions();
          setOutput("audit-export", { options: opts }, "Download Summary", { source: "audit" });
          addLog({ level: "success", message: "Filter options loaded" });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Retry — search blocked records ─────────────────────────────────
      case "audit-retry-search": {
        clearOutput();
        setOutput("audit-retry-search", {}, "Search Blocked Records", { source: "audit" });
        break;
      }

      // ── Retry — download error JSON (pick from batch list) ─────────────
      case "audit-retry-download": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches for error JSON download…" });
        try {
          const data = await fetchBatches();
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          // Only show partial/failed batches — those that have blocked records
          const retryable = list.filter(b => 
            ["PARTIAL", "FAILED"].includes(b.status?.toUpperCase()));
          setOutput(
            "audit-batch-list",
            retryable,
            "Select Batch — Download Error JSON",
            { source: "audit", action: "retry-download" }
          );
          addLog({ level: "success", message: `${retryable.length} batch(es) with errors` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Retry — upload fixed JSON ───────────────────────────────────────
      case "audit-retry-upload": {
        clearOutput();
        setOutput("audit-retry-upload", {}, "Upload Fixed JSON", { source: "audit" });
        break;
      }

      // ── Settings ────────────────────────────────────────────────────────
      case "audit-settings-buyers":
      case "audit-settings-factories":
      case "audit-settings-pairs": {
        const settingsMap = {
          "audit-settings-buyers":    { key: "buyers",    title: "Manage Buyers" },
          "audit-settings-factories": { key: "factories", title: "Manage Factories" },
          "audit-settings-pairs":     { key: "pairs",     title: "Manage Pairs" },
        };
        const { key, title } = settingsMap[ep.id];
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: `Loading ${title.toLowerCase()}…` });
        try {
          const fetchers = { buyers: fetchBuyers, factories: fetchFactories, pairs: fetchPairs };
          const data = await fetchers[key]();
          setOutput("audit-settings", data, title, { source: "audit", settingsKey: key });
          addLog({ level: "success", message: `Loaded ${(Array.isArray(data) ? data : data?.results ?? []).length} record(s)` });
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

  return <DashboardLayout onSelect={handleSelect} />;
}