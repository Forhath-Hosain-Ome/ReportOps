import { Btn, Section, IconBtn2 } from "../../primitives/index";
import { createHandleAction } from "../../hooks/useHandleActions";
import UploadForm from "../UploadForm";
import BatchList from "../BatchList";
import BatchDetail from "../BatchDetail";
import BatchLogsView from "../BatchLogsView";
import RetryModal from "../RetryModal";
import DownloadDropdown from "../DownloadDropdown";
import ReportCertBtn from "../ReportCertBtn";
import { STATUS_COLOR } from "../../constants"
import { useOutputStore } from "../../store/outputStore";
import ImageLogsView from "../ImageLogsView";
import ImageSettingsForm from "../ImageSettingsForm";


// ── Router component ──────────────────────────────────────────────────────────
export default function BatchOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();
  const onAction = createHandleAction(setOutput, setLoading, addLog, output);
  if (output.type === "image-settings") return <ImageSettingsForm data={output.data} />;
  if (output.type === "logs" && output.source === "image") return <ImageLogsView data={output.data} batchId={output.batchId} />;

  if (output.type === "batch-list")     return <BatchList data={output.data} onAction={onAction} />;
  if (output.type === "batch")          return <BatchDetail data={output.data} source={output.source} />;
  if (output.type === "logs")           return <BatchLogsView data={output.data} />;
  if (output.type === "batch-progress") return <UploadForm initData={output.data ?? {}} source={output.source} />;
  return null;
}
