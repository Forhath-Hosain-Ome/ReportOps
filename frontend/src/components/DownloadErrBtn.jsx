import { STATUS_COLOR } from "../constants"
import { Label, SectionTitle, PrimaryBtn, IconBtn } from "../primitives";
import { useState } from "react";
import { saveBlob } from "../constants"
import { downloadErrorJson } from "../services/finalSummaryApi";
import { ErrBtn } from "../primitives";

function DownloadErrBtn({ batchId, addLog }) {
  const [busy, setBusy] = useState(false);

  const handleDownload = async (e) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Downloading error JSON for Batch #${batchId}…` });
    try {
      const payload = await downloadErrorJson(batchId);
      const blob    = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      saveBlob(blob, `batch-${batchId}-errors.json`);
      addLog({ level: "success", message: `Error JSON downloaded for Batch #${batchId}` });
    } catch (err) {
      addLog({ level: "error", message: `Download failed: ${err.response?.data?.detail || err.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <ErrBtn handleDownload={handleDownload} busy={busy} batchId={batchId} />
  );
}

export default DownloadErrBtn;