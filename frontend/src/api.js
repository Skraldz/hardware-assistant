// Backend base URL. Override with VITE_API_BASE_URL if frontend and backend
// aren't on the same host. Default: same hostname the browser loaded this
// page from, on a port resolved at *container start* (window.__RUNTIME_CONFIG__,
// written by docker-entrypoint.sh from the API_PORT env var — see
// public/config.js) so changing APP_PORT in .env takes effect on
// `docker compose up` alone, without rebuilding the frontend image. Falls
// back to VITE_API_PORT (build-time, for `npm run dev`/`build` outside
// Docker) and then a hardcoded default.
function resolveApiPort() {
  const runtimePort = window.__RUNTIME_CONFIG__?.API_PORT;
  if (runtimePort && !runtimePort.includes("__API_PORT__")) return runtimePort;
  return import.meta.env.VITE_API_PORT || "8000";
}

const API_PORT = resolveApiPort();
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
    // Most backend errors set `detail` to a plain string already — only
    // stringify it when it isn't one (e.g. a list of validation errors),
    // so the message doesn't render wrapped in stray literal quotes.
    let message = response.statusText;
    if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (body?.detail) {
      message = JSON.stringify(body.detail);
    }
    throw new Error(message);
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
  extractComponent: (name, candidate, otherCandidates = []) =>
    request("/api/components/extract", {
      method: "POST",
      body: JSON.stringify({ name, candidate, other_candidates: otherCandidates }),
    }),

  recommend: (conversation, maxBuilds) =>
    request("/api/recommend", {
      method: "POST",
      body: JSON.stringify({ conversation, max_builds: maxBuilds }),
    }),

  listBackups: () => request("/api/backup"),
  createBackup: () => request("/api/backup", { method: "POST" }),
  restoreBackup: (name) =>
    request("/api/backup/restore", { method: "POST", body: JSON.stringify({ name, confirm: true }) }),

  listBuilds: () => request("/api/builds"),
  saveBuild: (build) => request("/api/builds", { method: "POST", body: JSON.stringify(build) }),
  deleteBuild: (id) => request(`/api/builds/${id}`, { method: "DELETE" }),
  completeBuild: (id) => request(`/api/builds/${id}/complete`, { method: "POST" }),
};
