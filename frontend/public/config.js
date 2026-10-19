// Placeholder, unprocessed by Vite (served/copied as-is from public/).
// docker-entrypoint.sh rewrites this at container *start* (not image build
// time) from the API_PORT env var, so changing APP_PORT in .env takes
// effect on `docker compose up` alone — see src/api.js.
window.__RUNTIME_CONFIG__ = { API_PORT: "__API_PORT__" };
