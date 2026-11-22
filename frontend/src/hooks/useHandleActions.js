import {
  fetchBatch as fetchBatchPuma,
  fetchBatchLogs as fetchBatchLogsPuma,
  downloadExcel as downloadExcelPuma,
  downloadCertificate as downloadCertificatePuma,
  downloadReportPDF as downloadReportPDFPuma,
} from "../services/pumaApi";
import {
  fetchBatch as fetchBatchImage,
  fetchBatchLogs as fetchBatchLogsImage,
  downloadReportPDF as downloadReportPDFImage,
  downloadReportDOCX as downloadReportDOCXImage,
} from "../services/defectImageApi";
import { saveBlob } from "../utils/fileUtils";


export const createHandleAction = (setOutput, setLoading, addLog, output = {}) => {
  const isImage = output?.source === "image";
  const fetchBatch     = isImage ? fetchBatchImage     : fetchBatchPuma;
  const fetchBatchLogs = isImage ? fetchBatchLogsImage : fetchBatchLogsPuma;
  const downloadPDF    = isImage ? downloadReportPDFImage  : downloadReportPDFPuma;
  const downloadDocx   = isImage ? downloadReportDOCXImage : downloadCertificatePuma;
  const downloadExcel  = isImage ? null : downloadExcelPuma;

  return async (action, id, meta = {}) => {
    switch (action) {
      case "view":
      case "retry": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("batch", data, `Batch #${id}`, { source: output?.source });
          addLog({ level: "info", message: `Loaded Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Batch #${id}` });
          setLoading(false);
        }
        break;
      }
      case "logs": {
        setLoading(true);
        try {
          const data = await fetchBatchLogs(id);
          setOutput("logs", data, `Logs · Batch #${id}`, { source: output?.source, batchId: id });
          addLog({ level: "info", message: `Logs loaded — ${data.count ?? data.total_failed} entries` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load logs for Batch #${id}` });
          setLoading(false);
        }
        break;
      }
      case "excel": {
        if (!downloadExcel) { addLog({ level: "warning", message: "Excel unavailable for image batches." }); break; }
        try {
          const blob = await downloadExcel(id);
          saveBlob(blob, `batch-${id}.xlsx`);
          addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
      }
      case "pdfs":
      case "certificates":
      case "all": {
        const reports = meta.reports?.length ? meta.reports : (await fetchBatch(id)).reports || [];
        for (const report of reports) {
          if (action === "pdfs" || action === "all") {
            try {
              const blob = await downloadPDF(report.id);
              const name = report.pdf_filename || `${report.style || report.folder_name || report.id}.pdf`;
              saveBlob(blob, name);
              addLog({ level: "success", message: `PDF: ${name}` });
            } catch (e) {
              addLog({ level: "error", message: `PDF failed: ${e.response?.data?.detail || e.message}` });
            }
          }
          if (action === "certificates" || action === "all") {
            try {
              const blob = await downloadDocx(report.id);
              const name = (report.pdf_filename || `${report.folder_name || report.id}`).replace(/\.(pdf|docx)$/i, ".docx");
              saveBlob(blob, name);
              addLog({ level: "success", message: `DOCX: ${name}` });
            } catch (e) {
              addLog({ level: "error", message: `DOCX failed: ${e.response?.data?.detail || e.message}` });
            }
          }
        }
        if ((action === "all") && downloadExcel && meta.hasExcel) {
          try {
            const blob = await downloadExcel(id);
            saveBlob(blob, `batch-${id}.xlsx`);
            addLog({ level: "success", message: `Excel downloaded` });
          } catch (e) {
            addLog({ level: "error", message: `Excel failed: ${e.response?.data?.detail || e.message}` });
          }
        }
        break;
      }
    }
  };
};