// Backend base URL. Override with VITE_API_BASE_URL if frontend and backend
// aren't on the same host. Default: same hostname the browser loaded this
// page from, on VITE_API_PORT (same port the backend's APP_PORT exposes) —
// avoids hardcoding the home server's IP anywhere.
const API_PORT = import.meta.env.VITE_API_PORT || "8000";
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(detail);
  }
  return body;
}

export const api = {
  getHealth: () => request("/api/health"),

  listComponents: (category) => request(`/api/components${category ? `?category=${category}` : ""}`),
  createComponent: (payload) => request("/api/components", { method: "POST", body: JSON.stringify(payload) }),
  deleteComponent: (id) => request(`/api/components/${id}`, { method: "DELETE" }),

  searchComponents: (name) =>
    request("/api/components/search", { method: "POST", body: JSON.stringify({ name }) }),
  extractComponent: (name, candidate) =>
    request("/api/components/extract", { method: "POST", body: JSON.stringify({ name, candidate }) }),

  recommend: (prompt, maxBuilds) =>
    request("/api/recommend", { method: "POST", body: JSON.stringify({ prompt, max_builds: maxBuilds }) }),

  listBackups: () => request("/api/backup"),
  createBackup: () => request("/api/backup", { method: "POST" }),
  restoreBackup: (name) =>
    request("/api/backup/restore", { method: "POST", body: JSON.stringify({ name, confirm: true }) }),
};
