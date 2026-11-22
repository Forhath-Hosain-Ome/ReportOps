import { useState } from "react";
import { useOutputStore } from "../store/outputStore";
import {
  downloadCertificate as downloadCertificatePuma,
  downloadReportPDF as downloadReportPDFPuma,
} from "../services/pumaApi";
import {
  downloadReportPDF as downloadReportPDFImage,
  downloadReportDOCX as downloadReportDOCXImage,
} from "../services/defectImageApi";
import { saveBlob } from "../utils/fileUtils";
import { Btn, Section } from "../primitives/index";
import UploadForm from "./UploadForm";
import BatchList from "./BatchList";
import BatchDetail from "./BatchDetail";
import BatchLogsView from "./BatchLogsView";
import RetryModal from "./RetryModal";
import DownloadDropdown from "./DownloadDropdown";

function ReportCertBtn({ reportId, styleName, pdfFilename, source = "puma" }) {
  const { addLog } = useOutputStore();
  const [busy, setBusy] = useState(false);
  const isImage = source === "image";
  const downloadFn  = isImage ? downloadReportPDFImage  : downloadReportPDFPuma;
  const downloadDocx = isImage ? downloadReportDOCXImage : downloadCertificatePuma;

  const handleClick = async (e) => {
    e.stopPropagation();
    setBusy(true);
    try {
      const blob = await downloadDocx(reportId);
      const name = pdfFilename
        ? pdfFilename.replace(/\.(pdf|docx)$/i, ".docx")
        : `${styleName || "report"}-${reportId}.docx`;
      saveBlob(blob, name);
      addLog({ level: "success", message: `Downloaded: ${name}` });
    } catch (err) {
      addLog({ level: "error", message: `Download failed: ${err.response?.data?.detail || err.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      title="Download DOCX"
      style={{
        background: "rgba(34,211,160,0.08)", border: "1px solid rgba(34,211,160,0.2)",
        color: "var(--color-success)", padding: "3px 10px", borderRadius: "4px",
        fontFamily: "var(--font-mono)", fontSize: "10px",
        cursor: busy ? "wait" : "pointer", opacity: busy ? 0.6 : 1, whiteSpace: "nowrap",
      }}
    >
      {busy ? "…" : "⬇ docx"}
    </button>
  );
}

export default ReportCertBtn;