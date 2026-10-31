import { defineConfig, devices } from "@playwright/test";

// All backend calls are intercepted via page.route() in the tests themselves
// (see e2e/mocks.js) -- these E2E tests never require a real backend, Ollama,
// or database (same "no test requires real services" rule the backend's own
// test suite follows, SPEC.md §9.1), only the frontend dev server itself.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
