# Architecture

See `SPEC.md` for the full technical spec and `docs/ai-log.md` for a phase-by-phase walkthrough of decisions and assumptions. This document gives an overview of how the pieces fit together.

## Services

```mermaid
flowchart LR
    Browser["Browser<br/>(user)"] -->|HTTP| Frontend
    Frontend["frontend<br/>(React + Vite)"] -->|HTTP, CORS| Backend
    Backend["backend<br/>(FastAPI)"] -->|SQL| DB[("db<br/>MariaDB")]
    Backend -->|HTTP, local network| Ollama["ollama<br/>(local LLM)"]
    Backend -->|HTTP, local network| SearXNG["searxng<br/>(web search)"]
    Backend -.->|backup only,<br/>only if BACKUP_BACKEND=azure| Azure[("Azure Blob<br/>Storage")]
```

| Service | Role |
|---|---|
| `db` | MariaDB. Hardware inventory (`components` table). |
| `backend` | FastAPI. All business logic: CRUD, compatibility engine, LLM pipeline, backup. |
| `ollama` | Local language model (default `qwen2.5:7b-instruct`). Runs **exclusively** on the home server. |
| `searxng` | Web search for `/api/components/search` (hardware specifications). |
| `frontend` | Minimal React UI. Talks directly to `backend` from the browser (not through a proxy). |

All services are defined in `docker-compose.yml` and started together with `docker compose up -d --build` (see README.md).

## Two main flows

### 1. Add a component (search → extract → confirm)

```
User types "RTX 2060 SUPER"
  → POST /api/components/search  → SearXNG → candidate list (title + snippet)
  → User picks a candidate
  → POST /api/components/extract → Ollama extracts specs from the snippet → shown for confirmation
  → User confirms (and adjusts quantity/condition if needed)
  → POST /api/components       → saved with specs_verified=true
```

If `ENABLE_WEB_LOOKUP=false`, the search step is skipped, and `/extract` instead asks Ollama to guess specs from its own knowledge (`specs_source=llm_extracted`, still `specs_verified=false` until the user confirms).

### 2. Recommend a build (free text → verified build)

```
User types "headless pc for local AI"
  → POST /api/recommend
    1. Ollama interprets the text into structured requirements (ProjectRequirements)
    2. Backend deterministically prefilters the inventory (quantity > 0, not faulty, hard minimum requirements)
    3. The compatibility engine (compatibility/) combines candidates and keeps only verified builds
    4. Ollama ranks the verified builds — invented build_id values are rejected
    5. The chosen build(s) are re-verified before the response is returned
  → Response: builds (with rule results + warnings), missing categories, and the status of each LLM call (ok/retried/fallback)
```

The core point: **the LLM proposes, the rules verify** (SPEC.md §2). No build is ever returned without `compatibility/engine.py` itself having run every rule against it.

## Data model

See SPEC.md §4 for the full data model. In short: a single `components` table with a discriminated JSON `specs` column per category (cpu/motherboard/ram/gpu/storage/psu/case/cooler), validated by Pydantic (`backend/app/schemas/components.py`) both when writing and reading.

## Security and responsible AI use (SPEC.md §9.3)

- **All AI inference runs locally.** `ollama` runs on the home server, inside the local Docker network. No prompt, project description, or component data is ever sent to an external AI service (OpenAI, Azure OpenAI, or similar).
- **Only inventory snapshots are sent to Azure**, and only when `BACKUP_BACKEND=azure` is explicitly selected in `.env` — see `docs/ai-log.md`'s Phase 4 entry. That's pure inventory data (component names, specs, quantities) — never prompts, LLM responses, or search results.
- **LLM output is never trusted unfiltered.** All structured LLM output is validated with Pydantic; invalid output gets one retry with the validation error fed back, then a deterministic fallback (see `backend/app/llm/parsing.py`). The ranking's `build_id` values are explicitly validated against the actual candidate list — an invented id is rejected.
- **Prompt injection.** User-controlled and web-search text (component names, project descriptions, search result snippets) is sent to the LLM wrapped in `<data>` blocks with an explicit instruction that the content is data, not commands. Literal `<`/`>` are escaped so an embedded fake closing tag can't break out of the block (see `backend/app/llm/prompts.py` and its tests).
- **The `specs_verified` flag.** Specs from the LLM or web lookup are always `specs_verified=false` until a user has actively confirmed them via the frontend.
- **No secrets in the repo.** `.env` is git-ignored; `.env.example` contains only placeholders. `GET /api/health`/`GET /api/backup` show the active backup destination, but never connection strings (explicitly tested, see `test_api.py`).
- **CORS is set to allow all origins** (`allow_origins=["*"]` in `backend/app/main.py`), because the frontend and backend run on different ports on a server whose LAN address isn't fixed. This is a deliberate simplification for a local/LAN deployment, not a publicly exposed service — it would be too permissive for a production deployment with real users.
