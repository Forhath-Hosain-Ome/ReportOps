import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchBatches } from "../services/pumaApi";
import filterByUser from "../utils/FilterByUser";
import DashboardLayout from "../components/layout/DashboardLayout";

export default function PumaPage() {
  const { user } = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();

  const handleSelect = async (ep) => {
    switch (ep.id) {
      case "upload":
        clearOutput();
        setOutput("batch-progress", null, "Upload PDFs");
        break;

      case "batch-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches({ _t: Date.now() });
          const filtered = filterByUser(data, user);
          setOutput("batch-list", filtered, "All Batches", { action: "view" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;

      default:
        addLog({ level: "error", message: `Unknown endpoint: ${ep.id}` });
        break;
    }
  };

  return <DashboardLayout onSelect={handleSelect} />;
}