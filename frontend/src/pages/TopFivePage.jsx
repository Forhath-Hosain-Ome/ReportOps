import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchJobs } from "../services/topFiveApi";
import filterByUser from "../utils/FilterByUser";
import DashboardLayout from "../components/layout/DashboardLayout";



export default function TopFivePage() {
  const { user } = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();

  const handleSelect = async (ep) => {
    switch (ep.id) {
      case "top5-upload":
        clearOutput();
        setOutput("top5-upload", null, "Upload Excel");
        break;

      case "top5-job-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching jobs…" });
        try {
          const data = await fetchJobs();
          const filtered = filterByUser(data, user);
          const count = (filtered.results || filtered).length;
          setOutput("top5-job-list", filtered, "All Jobs", { action: "view" });
          addLog({ level: "success", message: `Loaded ${count} job(s)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
    }
  };

  return <DashboardLayout onSelect={handleSelect} />;
}