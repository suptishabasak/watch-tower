export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function extractMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => (d.msg || "Invalid value").replace(/^Value error,\s*/, ""))
      .join(" ");
  }
  return `Something went wrong (HTTP ${status}).`;
}

async function request(path, { method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the Watchtower server. Check that the backend is running on port 8000.", 0);
  }

  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON response */
  }

  if (!res.ok) {
    if (!data && res.status >= 500) {
      throw new ApiError("Can't reach the Watchtower server. Check that the backend is running on port 8000.", res.status);
    }
    throw new ApiError(extractMessage(data, res.status), res.status);
  }
  return data;
}

export const api = {
  config: () => request("/config"),
  regionPreview: (url) => request("/region-preview", { method: "POST", body: { url } }),
  listMonitors: () => request("/monitors"),
  createMonitor: (payload) => request("/monitors", { method: "POST", body: payload }),
  updateMonitor: (id, payload) => request(`/monitors/${id}`, { method: "PATCH", body: payload }),
  deleteMonitor: (id) => request(`/monitors/${id}`, { method: "DELETE" }),
  checkNow: (id) => request(`/monitors/${id}/check`, { method: "POST" }),
  pause: (id) => request(`/monitors/${id}/pause`, { method: "POST" }),
  resume: (id) => request(`/monitors/${id}/resume`, { method: "POST" }),
  markSeen: (id) => request(`/monitors/${id}/seen`, { method: "POST" }),
  changes: (id) => request(`/monitors/${id}/changes`),
  snapshots: (id) => request(`/monitors/${id}/snapshots`),
  snapshot: (id, snapId) => request(`/monitors/${id}/snapshots/${snapId}`),
  compare: (id, a, b) => request(`/monitors/${id}/compare?a=${a}&b=${b}`),
  testNotification: (id) => request(`/monitors/${id}/test-notification`, { method: "POST" }),
  seedDemo: () => request("/demo/seed", { method: "POST" }),
  removeDemo: () => request("/demo", { method: "DELETE" }),
};