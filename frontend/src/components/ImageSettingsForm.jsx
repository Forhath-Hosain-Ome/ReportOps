import { useState } from "react";
import { updateSettings } from "../services/defectImageApi";

export default function ImageSettingsForm({ data }) {
  const [values, setValues] = useState(data);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  if (!data.can_manage) return null;
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const { retention_hours, image_width_px, image_height_px } = values;
      await updateSettings({ retention_hours, image_width_px, image_height_px });
      setMessage("Saved. New jobs will use these settings.");
    } catch (e) { setMessage(JSON.stringify(e.response?.data || e.message)); }
    finally { setBusy(false); }
  };
  return <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 480 }}>
    <h2>Image Processor settings</h2>
    {[["retention_hours", "Retention (hours)", 1, 720], ["image_width_px", "Image width (pixels)", 32, 4096], ["image_height_px", "Image height (pixels)", 32, 4096]].map(([key, label, min, max]) =>
      <label key={key}>{label}<input type="number" required min={min} max={max} value={values[key]} onChange={(e) => setValues({ ...values, [key]: Number(e.target.value) })} /></label>)}
    <button disabled={busy} type="submit">Save settings</button>
    <p role="status">{message}</p>
  </form>;
}
