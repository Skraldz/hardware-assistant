# Hardware Assistant

AI-driven hardware assistant and inventory system. See `SPEC.md` for the full technical spec and `CLAUDE.md` for the project rules. Exam requirements are summarized in `docs/exam-requirements.md`.

## Features

- **Hardware inventory**: register your own PC components (CPU, motherboard, RAM, GPU, storage, PSU, case, cooler) with category-specific specifications.
- **Automatic spec lookup**: type a component name (e.g. "RTX 2060 SUPER"), let the system search the web and extract specs with a local AI model — you confirm the result before it's saved.
- **AI-driven build recommendations**: describe a project in free text (e.g. "headless pc for local AI"), and get compatible builds suggested, assembled solely from your own inventory.
- **Deterministic compatibility checking**: every suggested build is verified by rule-based code (socket, RAM type, power draw, physical fit, etc.) — the AI never suggests anything the rules haven't approved.
- **Backup/restore**: back up the entire inventory to disk or Azure Blob Storage, and restore it with integrity checks (sha256, schema version).
- **Minimal web UI**: React frontend for inventory, recommendations, and backup, with light/dark mode and a Danish/English language picker (both remembered in the browser).

## How the system works

The core principle is **"the LLM proposes, the rules verify"** (see `SPEC.md` §2 and `docs/architecture.md` for a services diagram and the full walkthrough):

1. A local language model (Ollama) interprets the user's free text into structured requirements.
2. Deterministic Python code (`backend/app/compatibility/`) combines candidates from the inventory and keeps only the builds where every compatibility rule is satisfied.
3. The language model ranks and justifies among the already-verified builds — it can never suggest anything the code hasn't approved.
4. All structured AI output is validated with Pydantic; invalid output gets one retry, then a safe fallback. The system never crashes and never returns an unverified build because of a bad AI response.

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

## Backup: local or Azure

The inventory can be backed up to disk or to Azure Blob Storage. Switched **exclusively** via `.env` — no code changes:

```dotenv
BACKUP_BACKEND=local   # or: azure
```

- **`local`** (default): writes to `LOCAL_BACKUP_DIR` (default `/app/backups`), which is mounted as `./backups` on the server, so files survive a restart.
- **`azure`**: requires `AZURE_STORAGE_CONNECTION_STRING` **or** `AZURE_STORAGE_ACCOUNT_URL` (with `DefaultAzureCredential`) filled in `.env`. The container (`AZURE_BACKUP_CONTAINER`, default `inventory-backups`) is created automatically if it doesn't exist. If both are missing, **the backend fails at startup** — it never silently falls back to local storage.

The active backend and destination (never secrets) are shown in `GET /api/health` and `GET /api/backup`.

Backup endpoints: `POST /api/backup` (create a backup), `GET /api/backup` (list backups), `POST /api/backup/restore` (`{"name": "...", "confirm": true}` — replaces the entire inventory in a single transaction).

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

See `docs/ai-log.md` for a logged walkthrough of each phase (what was generated, assumptions, known risks, test coverage).
