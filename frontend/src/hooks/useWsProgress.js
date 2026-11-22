import { useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";

const WS_BASE_URL = import.meta.env.VITE_WS_URL || null;

/**
 * useWsProgress(batchId, { onProgress, onComplete, onError })
 *
 * Opens a WS to /ws/batches/<batchId>/progress/?token=<jwt>.
 * Automatically closes when batchId changes or the component unmounts.
 *
 * FIX — "WebSocket is closed before the connection is established" in dev:
 * React 18 Strict Mode intentionally runs every effect twice in development
 * (mount → unmount → mount) to surface side-effect bugs. The first mount opens
 * the socket, the cleanup immediately closes it, then the second mount opens
 * another one — but the first close arrives at the browser while the second
 * socket is still mid-handshake, producing the error.
 *
 * Fix: an `isCancelled` flag is captured in the cleanup closure. When React
 * tears down the first effect cycle, isCancelled flips to true and all handlers
 * on the orphaned socket become no-ops. The second cycle opens a fresh socket
 * that lives for the full lifetime of the component.
 */
export function useWsProgress(batchId, { onProgress, onComplete, onError, source = "puma" } = {}) {
  const wsRef    = useRef(null);
  const timerRef = useRef(null);

  // Stable refs for callbacks — always current but never trigger reconnect.
  const onProgressRef = useRef(onProgress);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef    = useRef(onError);
  useEffect(() => { onProgressRef.current = onProgress; }, [onProgress]);
  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);
  useEffect(() => { onErrorRef.current    = onError;    }, [onError]);

  useEffect(() => {
    if (!batchId) return;
    const token = useAuthStore.getState().access;
    if (!token)  return;

    // This flag is captured by every handler closure below.
    // The cleanup sets it to true so the orphaned socket from Strict Mode's
    // first cycle silently discards all events instead of calling stale callbacks.
    let isCancelled = false;

    const wsBase = WS_BASE_URL ? WS_BASE_URL.replace(/\/+$/g, "") : null;
    const namespace = source === "image" ? "image/batches" : "batches";
    const url = wsBase
      ? `${wsBase}/${namespace}/${batchId}/progress/?token=${token}`
      : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/${namespace}/${batchId}/progress/?token=${token}`;

    const openSocket = () => {
      if (isCancelled) return;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isCancelled) { ws.close(1000); return; }
        if (timerRef.current) clearTimeout(timerRef.current);
      };

      ws.onmessage = (e) => {
        if (isCancelled) return;
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }

        if (msg.event === "progress") onProgressRef.current?.(msg);
        if (msg.event === "complete") {
          onCompleteRef.current?.(msg);
          ws.close(1000);
        }
        if (msg.event === "error") onErrorRef.current?.(msg);
      };

      ws.onclose = (e) => {
        if (isCancelled) return;
        if (e.code !== 1000 && e.code !== 4401 && e.code !== 4404) {
          timerRef.current = setTimeout(openSocket, 3000);
        }
      };

      ws.onerror = () => {
        if (isCancelled) return;
        ws.close();
      };
    };

    openSocket();

    return () => {
      isCancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      const currentWs = wsRef.current;
      if (currentWs && currentWs.readyState === WebSocket.OPEN) {
        currentWs.close(1000);
      }
      wsRef.current = null;
    };
  }, [batchId, source]); // only reconnect when the batch actually changes
}