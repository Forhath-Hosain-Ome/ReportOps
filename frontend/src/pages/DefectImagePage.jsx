import { useOutputStore } from "../store/outputStore";
import { fetchBatches, fetchReports, fetchSettings } from "../services/defectImageApi";
import { useEffect, useState } from "react";
import DashboardLayout from "../components/layout/DashboardLayout";

export default function DefectImagePage() {
  const [settings, setSettings] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetchSettings().then((value) => { if (!cancelled) setSettings(value); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  

  const handleSelect = async (ep) => {
    
    switch (ep.id) {
      case "image-settings":
        setOutput("image-settings", await fetchSettings(), "Image Processor settings", { source: "image" });
        break;
      // ── Direct actions ────────────────────────────────────────────────────
      case "upload":
        clearOutput();
        setOutput("batch-progress", null, "Upload Folder's", { source: "image" });
        break;

      case "batch-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches({ _t: Date.now() });
          const filtered = data; // The Image API already enforces ownership on the server.
          setOutput("batch-list", filtered, "All Batches", { action: "view", source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
       
      case "report-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching reports…" });
        try {
          const data = await fetchReports();
          const filtered = data;
          setOutput("report-list", filtered, "All Reports", { action: "view", source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
    }
  };

  return <DashboardLayout onSelect={handleSelect} extraSections={settings?.can_manage ? [{ label: "SETTINGS", endpoints: [{ id: "image-settings", label: "Image settings", icon: "⚙", method: "GET", path: "/settings/" }] }] : []} />;
}
