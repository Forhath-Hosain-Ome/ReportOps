export function isAbandonedImagePublication(batch) {
  return batch?.status === "PENDING"
    && ["REQUESTED", "PUBLISHING"].includes(batch.dispatch_state)
    && Boolean(batch.lease_expires_at)
    && new Date(batch.lease_expires_at).getTime() <= Date.now();
}
