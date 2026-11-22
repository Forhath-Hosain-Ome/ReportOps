export function saveBlob(blob, filename) {
  filename = blob?.filename || filename;
  blob = blob?.blob || blob;
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}