import { useAuthStore }   from "../store/authStore";
import { useRef, useEffect } from "react";

function useAuditWs(batchId, { onProgress, onComplete, onError } = {}) {
  const wsRef  = useRef(null);
  const cbsRef = useRef({ onProgress, onComplete, onError });
  useEffect(() => { cbsRef.current = { onProgress, onComplete, onError }; });

  useEffect(() => {
    if (!batchId) return;
    const token = useAuthStore.getState().access;
    if (!token) return;
    let cancelled = false;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/audit-batches/${batchId}/progress/?token=${token}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      if (cancelled) return;
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.event === "progress") cbsRef.current.onProgress?.(msg);
      if (msg.event === "complete") { cbsRef.current.onComplete?.(msg); ws.close(1000); }
      if (msg.event === "error")    cbsRef.current.onError?.(msg);
    };
    ws.onerror = () => ws.close();

    return () => {
      cancelled = true;
      if (ws.readyState === WebSocket.OPEN) ws.close(1000);
    };
  }, [batchId]);
}

export default useAuditWs;