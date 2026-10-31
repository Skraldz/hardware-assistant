// Canned API responses + a single mockApi() helper that intercepts every
// backend call the app makes, shaped to match the real response schemas
// (backend/app/schemas/*.py). Keeping all of this in one place means a test
// only overrides the handful of fields it actually cares about.

export const DEFAULT_HEALTH = {
  status: "ok",
  db: "ok",
  ollama: "ok",
  storage: "ok",
  backup_backend: "local",
  backup_destination: "/app/backups",
  enable_web_lookup: true,
};

export const SAMPLE_COMPONENTS = [
  {
    id: 1,
    name: "AMD Ryzen 5 3600",
    manufacturer: "AMD",
    quantity: 1,
    condition: "used",
    specs_source: "manual",
    specs_verified: true,
    notes: null,
    category: "cpu",
    specs: {
      category: "cpu",
      socket: "AM4",
      cores: 6,
      threads: 12,
      tdp_w: 65,
      integrated_graphics: false,
      memory_type: ["DDR4"],
    },
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
  {
    id: 2,
    name: "NVIDIA GeForce RTX 2060 6GB",
    manufacturer: "NVIDIA",
    quantity: 1,
    condition: "used",
    specs_source: "manual",
    specs_verified: true,
    notes: null,
    category: "gpu",
    specs: {
      category: "gpu",
      vram_gb: 6,
      tdp_w: 160,
      length_mm: 229,
      pcie_power_connectors: ["8-pin"],
      vendor: "nvidia",
    },
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
];

export const SAMPLE_RECOMMEND_RESPONSE = {
  builds: [
    {
      components: [
        { id: 1, category: "cpu", name: "AMD Ryzen 5 3600" },
        { id: 2, category: "gpu", name: "NVIDIA GeForce RTX 2060 6GB" },
      ],
      rule_results: {},
      warnings: [],
      reason: "Meets the stated requirements.",
      score: 97,
    },
  ],
  missing: [],
  llm_used: { interpret: "ok", rank: "ok", reply: "ok" },
  assistant_message: "Here is a build from your inventory that fits what you asked for.",
};

export const SAMPLE_SEARCH_CANDIDATES = {
  query: "RTX 2060 SUPER",
  candidates: [
    {
      title: "NVIDIA GeForce RTX 2060 SUPER Specs | TechPowerUp GPU Database",
      url: "https://example.com/rtx-2060-super",
      snippet: "8 GB GDDR6, 175 W TDP.",
    },
  ],
};

export const SAMPLE_SAVED_BUILDS = [
  {
    id: 1,
    name: null,
    components: [
      { id: 1, category: "cpu", name: "AMD Ryzen 5 3600" },
      { id: 2, category: "gpu", name: "NVIDIA GeForce RTX 2060 6GB" },
    ],
    reason: "Meets the stated requirements.",
    completed: false,
    created_at: "2026-01-01T00:00:00",
    completed_at: null,
  },
];

export const SAMPLE_BACKUPS = {
  backup_backend: "local",
  destination: "/app/backups",
  backups: [],
};

async function fulfillJson(route, body, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

/** All tabs stay mounted simultaneously (App.jsx), hidden rather than
 * unmounted -- this locator scopes queries to only the currently visible
 * one, avoiding strict-mode ambiguity against identical text sitting
 * (hidden) in another tab. */
export function activePane(page) {
  return page.locator("main > div:not([hidden])");
}

/** Intercepts every /api/* call the app makes with sensible defaults,
 * overridable per test via the `overrides` map (path pattern -> response). */
export async function mockApi(page, overrides = {}) {
  const components = overrides.components ?? SAMPLE_COMPONENTS;
  const health = overrides.health ?? DEFAULT_HEALTH;
  const recommend = overrides.recommend ?? SAMPLE_RECOMMEND_RESPONSE;
  const search = overrides.search ?? SAMPLE_SEARCH_CANDIDATES;
  const builds = overrides.builds ?? SAMPLE_SAVED_BUILDS;
  const backups = overrides.backups ?? SAMPLE_BACKUPS;

  await page.route("**/api/health", (route) => fulfillJson(route, health));
  await page.route("**/api/components", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(
        route,
        { ...components[0], id: components.length + 1, ...JSON.parse(route.request().postData()) },
        201,
      );
    }
    return fulfillJson(route, components);
  });
  await page.route("**/api/components/*", (route) => {
    if (route.request().method() === "DELETE") return route.fulfill({ status: 204 });
    return route.continue();
  });
  await page.route("**/api/components/search", (route) => fulfillJson(route, search));
  await page.route("**/api/components/extract", (route) =>
    fulfillJson(route, {
      name: "Extracted part",
      specs: SAMPLE_COMPONENTS[1].specs,
      specs_source: "web_lookup",
      llm_used: "ok",
    }),
  );
  await page.route("**/api/recommend", (route) => fulfillJson(route, recommend));
  await page.route("**/api/builds", (route) => {
    if (route.request().method() === "POST") return fulfillJson(route, builds[0], 201);
    return fulfillJson(route, builds);
  });
  await page.route("**/api/builds/*/complete", (route) =>
    fulfillJson(route, { id: 1, completed: true, removed_component_ids: [1, 2] }),
  );
  await page.route("**/api/builds/*", (route) => {
    if (route.request().method() === "DELETE") return route.fulfill({ status: 204 });
    return route.continue();
  });
  await page.route("**/api/backup", (route) => fulfillJson(route, backups));
}
