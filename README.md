# Hardware Assistant

AI-driven hardware assistant and inventory system. See `SPEC.md` for the full technical spec and `CLAUDE.md` for the project rules. Exam requirements are summarized in `docs/exam-requirements.md`.

## Features

- **Hardware inventory**: register your own PC components (CPU, motherboard, RAM, GPU, storage, PSU, case, cooler) with category-specific specifications.
- **Automatic spec lookup**: type a component name (e.g. "RTX 2060 SUPER"), let the system search the web, fetch and clean the actual page you pick (not just the search engine's short preview of it), and extract specs with a local AI model — you confirm the result before it's saved. The page the specs came from is recorded, and the component's name links to it in the inventory, so a claim can be checked later.
- **AI-driven build recommendations**: describe a project in free text (e.g. "headless pc for local AI"), and get compatible builds suggested, assembled solely from your own inventory.
- **Deterministic compatibility checking**: every suggested build is verified by rule-based code (socket, RAM type, power draw, physical fit, etc.) — the AI never suggests anything the rules haven't approved.
- **Backup/restore**: back up the entire inventory to disk or Azure Blob Storage, and restore it with integrity checks (sha256, schema version).
- **Minimal web UI**: React frontend for inventory, recommendations, and backup, with light/dark mode and a Danish/English language picker (both remembered in the browser).

## How the system works

The core principle is **"the LLM proposes, the rules verify"** (see `SPEC.md` §2 and `docs/architecture.md` for a services diagram and the full walkthrough):

1. A local language model (Ollama) interprets the user's free text into structured requirements.
2. Deterministic Python code (`backend/app/compatibility/`) combines candidates from the inventory and keeps only the builds where every compatibility rule is satisfied.
3. A diversity-aware step picks the pool that gets ranked, spanning distinct CPUs and GPUs — without it, one high-scoring CPU fills the pool and every suggestion is a minor variation of the same build.
4. The language model ranks and justifies among the already-verified builds — it can never suggest anything the code hasn't approved.
5. All structured AI output is validated with Pydantic; invalid output gets one retry, then a safe fallback. The system never crashes and never returns an unverified build because of a bad AI response.

All AI inference runs locally (Ollama on your own server) — only inventory snapshots ever leave the machine, and only if you choose Azure as the backup destination.

## Requirements

- **Docker** and **Docker Compose** — to run the whole stack (database, backend, local LLM, web search, frontend) with one command.
- Enough memory/disk space to run a local language model in Ollama (default `qwen2.5:7b-instruct`). A GPU is recommended for reasonable response times, but not required — see the GPU passthrough block in `docker-compose.yml`.
- For local development without Docker: **Python 3.12+** (backend) and **Node.js 20+** (frontend).
- No Azure account is required by default — backup uses local disk space unless `BACKUP_BACKEND=azure` is explicitly chosen in `.env`.

## Run the project

```bash
cp .env.example .env   # fill in passwords
docker compose up -d --build
```

The backend starts on `http://localhost:8000` (see `/docs` for OpenAPI). The frontend starts on `http://localhost:4173`. The database is created and seeded automatically on first start (empty database).

If you open the frontend from a different machine than the server (e.g. `http://192.168.1.50:4173`), it finds the backend on the same hostname, port `APP_PORT`, automatically — no configuration needed.

### A setting worth knowing about

`OLLAMA_NUM_CTX` (default `8192`) is set explicitly, because Ollama otherwise applies its own
context window and **does not fail on overflow — it silently drops the oldest tokens**. For
`/api/components/extract` that means dropping the fetched page text the web lookup exists to
supply, and the model then fills the fields from its own vague recollection of the product
instead. Measured against `qwen2.5:7b-instruct`: at a 2048 context only 2 of 5 extracted values
matched the page, at 4096 and 8192 all 5 did.

```bash
cd backend
python -m scripts.measure_prompt_budget          # prompt sizes; needs nothing running
python -m scripts.measure_prompt_budget --live   # also calls a running Ollama
# in Docker: docker compose exec backend python -m scripts.measure_prompt_budget --live
```

Lower it first if the host is short on memory — a larger context costs KV-cache per loaded model.

## Backup: local or Azure

The inventory can be backed up to disk or to Azure Blob Storage, picked per backup from the Backup tab (or per API call) — not fixed once at deployment:

```dotenv
BACKUP_BACKEND=local   # the default destination when a call doesn't say which one to use
AZURE_STORAGE_CONNECTION_STRING=...   # or AZURE_STORAGE_ACCOUNT_URL — either makes Azure selectable at all
```

- **`local`**: writes to `LOCAL_BACKUP_DIR` (default `/app/backups`), which is mounted as `./backups` on the server, so files survive a restart. Always available.
- **`azure`**: requires `AZURE_STORAGE_CONNECTION_STRING` **or** `AZURE_STORAGE_ACCOUNT_URL` (with `DefaultAzureCredential`) filled in `.env` — fill in either one to make Azure selectable as an *option*, independently of whether `BACKUP_BACKEND` itself is set to `azure`. The container (`AZURE_BACKUP_CONTAINER`, default `inventory-backups`) is created automatically if it doesn't exist. If `BACKUP_BACKEND=azure` is set as the *default* without either credential, **the backend fails at startup** — it never silently falls back to local storage; asking for `azure` explicitly on a single call without credentials configured returns a 400 instead.

The Backup tab shows which backends are actually usable and lets you switch between them; `GET /api/health`/`GET /api/backup` show the active backend and destination (never secrets).

Backups are `.xlsx` spreadsheets — one sheet per hardware category (cpu, motherboard, ram, gpu, storage, psu, case, cooler), plus a `Builds` sheet for everything saved from the Builds tab and a `Metadata` sheet (schema version, timestamp, integrity hash) — directly openable and reviewable in Excel/LibreOffice/Google Sheets, not just a flat JSON blob. Backups created before this format existed (plain `.json`) are still listed and restorable.

Backup endpoints: `POST /api/backup` (`{"backend": "local" | "azure" | null}`, create a backup — `null`/omitted uses the configured default), `GET /api/backup?backend=...` (list backups for a backend), `POST /api/backup/restore` (`{"name": "...", "confirm": true, "backend": "..."}`  — replaces the entire inventory in a single transaction).

## Development and tests (without Docker)

Tests run against SQLite in-memory and require neither MariaDB, Ollama, nor Azure.

```bash
cd backend
pip install -e ".[dev]"
ruff check .
ruff format .
pytest --cov
```

## Frontend development (without Docker)

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, expects the backend on :8000
```

## Frontend end-to-end tests (Playwright)

Like the backend's test suite, these never require a real backend, Ollama, or database — every `/api/*` call is intercepted with canned responses (`frontend/e2e/mocks.js`). Only the frontend dev server itself is needed; Playwright starts it automatically.

```bash
cd frontend
npm install
npx playwright install chromium   # one-time browser download
npm run test:e2e
```

## Status

248 backend tests and 23 end-to-end tests, 96% coverage overall and 100% on the compatibility
rules and the build engine. No test requires Ollama, MariaDB or Azure, so the suite runs
deterministically in about three seconds.

See `docs/ai-log.md` for a logged walkthrough of each phase — what was generated, which
assumptions were made, known risks, and the tests covering it. Every bug found in running
deployment has a regression test that was first verified to fail against the pre-fix code.

## Known limitations

These are open and documented rather than hidden. Each has a proposed fix and the design
questions that are actually blocking it:

- [#7](https://github.com/Skraldz/hardware-assistant/issues/7) — the model only partially fills
  the preference flags, so some different prompts return identical builds.
- [#8](https://github.com/Skraldz/hardware-assistant/issues/8) — build diversification can force
  a contextually poor third suggestion when only two good options exist.

Beyond these: specification values come from web pages and the model's general knowledge rather
than from datasheets, so the system verifies *compatibility* but cannot verify that the
specifications themselves are correct. That is why extraction always requires user confirmation.
