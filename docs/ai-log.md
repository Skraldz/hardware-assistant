# AI development log

See SPEC.md §10 for the format. Each entry covers one phase/feature. "Review" is filled in by the student.

## 2026-10-31 – Clarifying questions, manual-add JSON template, scrollable inventory

**Generated:**
- `backend/app/schemas/requirements.py`: `ProjectRequirements.clarifying_question: str | None = None`. Set by the requirements-interpretation LLM when the conversation so far is too vague to confidently fill in the other fields (no hint of intended use, performance target, display-output need, or power/budget constraints).
- `backend/app/llm/prompts.py`: `REQUIREMENTS_SYSTEM_PROMPT` instructs the LLM to ask exactly one specific clarifying question when genuinely needed, to still fill in a best guess for every other field regardless (so a build is shown even before the user answers), and to stop asking once the conversation already gives it enough or the user has moved on without answering.
- `backend/app/pipeline/recommend.py`: `_assistant_message()` now also takes `requirements` and appends `requirements.clarifying_question` (if set) to the chat reply.
- `frontend/src/components/InventoryView.jsx`: `SPEC_TEMPLATES`, one per category, listing every field `schemas/components.py` accepts for it. The manual-add JSON box now starts from the full template for the selected category (not just `{"category": "cpu"}`) and regenerates when the category dropdown changes (previously it silently kept showing the old category's JSON after switching).
- `frontend/src/styles.css` / `InventoryView.jsx`: the inventory table is wrapped in a `.table-scroll` container (`max-height: 50vh`, `overflow-y: auto`, sticky header) so a 55+ row inventory no longer pushes the "add component" sections off-screen.

**Assumptions:**
- **The clarifying question is additive, not a separate conversational mode.** The pipeline still always runs end-to-end and returns builds every turn (using the LLM's best guess for whatever wasn't asked about) — the question is just prepended to the chat reply. A stricter "pause and wait for an answer before showing any build" flow was considered and rejected: it would need new state (has this question been asked/answered yet?) the stateless backend doesn't otherwise need, for a marginal UX gain over "here's a reasonable guess, and by the way...".
- **Switching the manual-add category always replaces the JSON box wholesale**, discarding whatever the user had typed. Consistent with the fact that a category switch already requires the JSON's `category` field to match (existing mismatch guard) — treated as "starting a new entry for a different category," not an edit to preserve.

**Known risks / weaknesses:**
- **The clarifying-question behavior is implemented but not yet verified against a real Ollama response** — the home-server deployment had no model pulled at all (`ollama list` was empty) when this was built, so every LLM call was hitting the deterministic fallback, not real model output. Once a model is pulled, this should be checked manually: does the model actually ask a sensible, single question, and does it stop asking once the user answers?
- **No limit on how many turns a clarifying question can keep being asked** beyond the prompt's own instruction not to repeat itself — relies entirely on the LLM following that instruction, with no code-level guard (e.g. "never ask twice in a row"). Worth revisiting if it turns out to pester the user in practice.

**Tests covering it:**
- `test_pipeline.py::test_clarifying_question_is_surfaced_in_the_assistant_message`: a fixture response with `clarifying_question` set produces an `assistant_message` containing that question.
- `ruff check`/`ruff format --check`/`pytest --cov` green: 153 tests, 95% overall coverage.
- Frontend: `npm run build` clean. Manually verified in a real browser: switching the manual-add category dropdown (cpu → gpu) correctly regenerates the JSON box with that category's full field list; the inventory table scrolls within its own box instead of pushing the add-component forms off-screen.

**Review (filled in by the student):**

## 2026-10-31 – Interactive recommend chat, sortable/categorized inventory, search-quality fix

**Generated:**
- `backend/app/schemas/builds.py`: `ConversationMessage` (`role`, `content`) and `RecommendRequest.conversation: list[ConversationMessage]` replace the old single `prompt: str` field. `RecommendResponse` gains `assistant_message: str`.
- `backend/app/routers/recommend.py`: `_build_transcript()` flattens the conversation into one `"role: content"`-per-line string before handing it to the existing single-prompt pipeline — the pipeline itself (`pipeline/recommend.py`) doesn't need to know multi-turn chat exists at all.
- `backend/app/llm/prompts.py`: `REQUIREMENTS_SYSTEM_PROMPT` and `build_requirements_prompt()` updated to tell the LLM the input may be a multi-turn transcript, where later user turns refine or override earlier ones and assistant turns are prior responses included only as context.
- `backend/app/pipeline/recommend.py`: `_assistant_message()` synthesizes a short, deterministic natural-language summary (e.g. "Found 3 compatible builds. Top pick: ...") from the already-computed `builds`/`missing`, attached to every `RecommendResponse`.
- `frontend/src/components/RecommendView.jsx`: rewritten from a single-shot form into a chat log — every user message and assistant reply (with that turn's builds) is appended to `messages` state and resent in full on the next turn; a "New conversation" button resets it.
- `frontend/src/components/InventoryView.jsx`: category filter chips (`All` + each category) and clickable, sortable column headers (category/name/quantity/condition/specs verified, with a ▲/▼ indicator), both purely client-side over the already-fetched inventory.
- `backend/app/search/client.py`: `_build_query()` appends `"specifications"` to the search query and excludes a short list of marketplace/retailer domains (`amazon.com`, `ebay.com`, `dba.dk`, `newegg.com`) via `-site:` — the extraction LLM was getting marketing copy from retailer listings instead of real spec numbers to extract from.
- `docs/architecture.md`: flow #2 updated to describe the conversation transcript step and the `assistant_message` field.

**Assumptions:**
- **The backend stays stateless for the conversation** — no new DB table, no session storage. The frontend resends the full conversation on every turn, matching the project's existing "no persistence beyond the inventory itself" posture and avoiding new infrastructure for a feature that's still a thin layer over the existing single-prompt pipeline.
- **The assistant's reply text is deterministic, not an extra LLM call.** It's built entirely from data the pipeline already computed (`builds`, `missing`) — there's nothing left for an LLM to add, and it avoids doubling the number of LLM calls per turn.
- **`-site:` exclusion syntax in the SearXNG query is standard search-operator syntax** (Google/Bing/DuckDuckGo etc. all honor it in plain query text), not a SearXNG-specific feature — chosen over `site:`-only inclusion of a curated "good" domain allowlist, which risked zero results for categories (motherboard/PSU/case/cooler) that general spec-database sites don't cover well.
- **Inventory sorting/filtering is entirely client-side** over the already-fetched component list — proportionate at 55 (or even a few hundred) components; `GET /api/components?category=` already exists server-side if this ever needs to move server-side for a much larger inventory.

**Known risks / weaknesses:**
- **The `-site:` exclusion query has not been verified against a real, running SearXNG instance** (no SearXNG in this session, same caveat as Phase 3's original search integration). If an underlying engine ignores or mishandles the operator, the practical effect degrades to the plain `"<name> specifications"` keyword boost, not a hard failure — but this should be checked manually on the home server, and the excluded-domain list (`backend/app/search/client.py`'s `_EXCLUDED_DOMAINS`) extended if other marketplace sites keep showing up.
- **No automated tests for the frontend chat UI or inventory sorting/filtering** — same rationale as the rest of the frontend (SPEC doesn't require it); verified manually in a real browser against a local backend (see Tests).
- **Multi-turn refinement quality depends entirely on the LLM actually honoring the "later turns override earlier ones" instruction** — not verified against a real Ollama in this session (no Ollama running locally); only verified that the full transcript reaches the prompt correctly (see Tests) and that the conversation UI and deterministic fallback path work end-to-end.

**Tests covering it:**
- `test_api_llm_endpoints.py`: `/api/recommend` accepts a `conversation` list and returns `assistant_message`; a dedicated test asserts the full transcript (both user turns, labeled `user:`/`assistant:`) reaches the requirements-interpretation LLM prompt; an empty `conversation` is rejected with 422.
- `test_search_client.py`: `_build_query()` appends `"specifications"` and excludes each configured domain; `SearxngClient.search()` is asserted to actually send the transformed query to SearXNG (mocked `httpx.get`, never a real SearXNG, per SPEC.md §9.1).
- `ruff check`/`ruff format --check`/`pytest --cov` green: 152 tests, 95% overall coverage.
- Frontend: `npm run build` clean. Manually verified in a real browser (Claude in Chrome) against a local backend (SQLite, `ENABLE_WEB_LOOKUP=false`, no Ollama running): inventory category chips filter correctly, column headers sort ascending/descending with a visible indicator; the recommend chat sends the first message, shows the assistant's reply and build cards, accepts a follow-up message, and correctly keeps both turns' builds visible in the log (the LLM calls themselves hit the fast `LLMUnavailableError` fallback path, since no Ollama was running — the architecture was verified end-to-end, not live LLM reasoning quality).

**Review (filled in by the student):**

## 2026-10-19 – Frontend: light/dark mode + language picker (Danish/English)

**Generated:**
- `frontend/src/theme/ThemeContext.jsx`: React context for light/dark mode. Starts from a saved choice in `localStorage`, otherwise `window.matchMedia("(prefers-color-scheme: dark)")`. The toggle sets `data-theme` on `<html>` and saves the choice.
- `frontend/src/styles.css`: rewritten to CSS custom properties (`--color-*`) defined on `:root` (light) and overridden under `:root[data-theme="dark"]`. The header bar deliberately keeps its dark color in both themes (a consistent branding bar, a common dashboard pattern) — only the content surfaces (`body`, `section`, `nav`, table, forms) switch.
- `frontend/src/i18n/translations.js` + `LanguageContext.jsx`: a simple, hand-written dictionary (`da`/`en`) + a `t(key, ...args)` function via React context, instead of a library like react-i18next — judged proportionate for a "secondary" frontend with a limited number of UI strings. The language choice is saved in `localStorage` (default `da`).
- All four components (`App.jsx`, `HealthBadge.jsx`, `InventoryView.jsx`, `RecommendView.jsx`, `BackupView.jsx`) rewritten to use `t(...)` instead of hardcoded Danish text. `App.jsx` got a language `<select>` and a theme-toggle button in the header, next to `HealthBadge`.
- `README.md`: the "Minimal web UI" bullet now mentions light/dark mode and the language picker.

**Assumptions:**
- **Only UI chrome is translated** (labels, buttons, headings, static messages) — **not** backend-generated content: rule messages, LLM justifications, API error messages (`err.message`), or component category/condition values in the table (`cpu`, `used`, etc.). That would require either translating server-side (backend prompts and error messages were written in Danish at the time, per CLAUDE.md rule 6 as it stood then) or duplicating all business-logic text in the frontend dictionary — both out of scope for a secondary frontend. Documented directly in `translations.js`'s header comment.
- **A binary light/dark toggle, not a three-way "light/dark/system" menu.** The default follows the system preference on first visit (`prefers-color-scheme`), but once the user has clicked, the choice is explicit and persists — a "follow system" mode would require a third UI state and a listener on `matchMedia` changes, judged as unnecessary complexity.
- **The default prompt in the Recommend tab ("headless pc for local AI") is also translated** (the `defaultPrompt` key), so it matches the active language on first render — not a requirement, but a small detail to avoid a Danish example text in an otherwise English UI.
- **`localStorage` is used for both choices** (same pattern for both, and the same error handling already established in the project) — falls back to an in-memory default (no persistence) if unavailable (private browsing, blocked storage), without failing.

**Known risks / weaknesses:**
- **No automated tests for theme/language** — same rationale as the rest of the frontend (see the Phase 5 entry): the spec doesn't require frontend tests, and Vitest/React Testing Library hasn't been added. Verified manually (see below).
- **Category/condition values in the inventory table remain English abbreviations** (`cpu`, `gpu`, `new`, `faulty`, etc.) regardless of language choice — they are backend enum values, not translated UI text. Short, technical, and understandable in both languages, but worth mentioning if an examiner asks why the "Inventory" tab isn't 100% translated.

**Tests covering it (manual verification, since this is frontend UI):**
- `npm run build` runs without errors.
- Verified in a real browser (Claude in Chrome) against a real, running local backend: the theme starts in dark mode (matching the dev machine's OS `prefers-color-scheme: dark`), toggling to light mode confirmed via computed styles (`document.documentElement.getAttribute("data-theme")`, `body`/`section`/`nav` background colors) — not just a screenshot, since the header bar's deliberately unchanged dark color made a purely visual check misleading at first glance.
- Language switched to English via the `<select>`: all three tabs' labels, headings, table columns, and the default prompt all switched correctly.
- **Both choices reload correctly after a full page reload** (confirms `localStorage` persistence).
- No errors in the browser console throughout.

**Review (filled in by the student):**

## 2026-10-19 – Code review (/code-review) + fixes

Run after Phase 5. A multi-agent code review found 10 confirmed findings across frontend and backend; all are fixed in this entry.

**Generated/fixed:**
- **`InventoryView.jsx` — the "Extract directly" button was dead under the default configuration.** The backend requires a `candidate` when `ENABLE_WEB_LOOKUP=true` (the default), but the button always called `extractComponent(name, null)`. Fixed by extending the pattern `HealthBadge`/`BackupView` already used (show what the backend reports, never assume): `/api/health` now exposes `enable_web_lookup`, and `InventoryView` fetches it and shows **either** the "Search" button (when enabled) **or** a direct-extract button (when disabled) — never a button guaranteed to fail.
- **`InventoryView.jsx` — name/specs could get out of sync.** `handleConfirmSave` read the *current* `searchName` state instead of the name at extraction time, and the search field wasn't locked during review. Fixed: the name is frozen in a separate `confirmName` state at extraction time, and the input field is disabled while a result is under review.
- **`InventoryView.jsx` — a race between concurrent search/extract calls.** A slower, already-superseded call could overwrite a newer result when it finally finished. Fixed with a simple request-sequence counter (`useRef`) that ignores responses from a call that's been superseded by a newer one.
- **`InventoryView.jsx` — manual add could silently drop fields.** The `category` dropdown always overwrote the specs JSON's `category`, and since no spec model has `extra="forbid"`, fields from a mismatched category disappeared silently. Fixed: if the JSON's `category` exists and differs from the dropdown, an error is shown instead of silently overwriting it.
- **`backend/app/main.py` — 500 errors were missing CORS headers.** `@app.exception_handler(Exception)` didn't behave as expected: FastAPI specifically moves a handler registered on the `Exception` type itself to `ServerErrorMiddleware`, which Starlette always places **outside** user-defined middleware (including `CORSMiddleware`) — found because my first fix failed a test that directly reproduced the failure scenario (see Known risks). The correct fix is a plain `BaseHTTPMiddleware`, added *before* `CORSMiddleware` (so it ends up inside CORS in the call stack), which itself catches exceptions and returns a normal `Response` object. At the same time, `OllamaClient`/`SearxngClient`'s `httpx` calls are now wrapped and raise `LLMUnavailableError`/`SearchUnavailableError` instead of leaking raw `httpx` exceptions — `call_llm_with_retry` now goes straight to the fallback on an unreachable Ollama (without wasting a retry attempt on a failure that won't fix itself), and `/api/components/search` returns a clean 503 on an unreachable SearXNG.
- **`BackupView.jsx` — concurrent destructive actions weren't prevented.** The `disabled` check only covered the row in progress; other "Restore" buttons and "Create backup now" were still clickable during an in-progress restore. Fixed with one global `activeAction` state that locks every action button while one is in progress.
- **`api.js` — error messages were shown with redundant quote marks.** `JSON.stringify(detail)` was used regardless of whether `detail` was already a plain string (which most backend errors are). Fixed to only stringify when `detail` isn't already a string.
- **`frontend/Dockerfile` — the build didn't use the committed lockfile.** `npm install` ran before `package-lock.json` was even copied in. Fixed: copy both files together and use `npm ci`.
- **`docker-compose.yml`/`Dockerfile` — the backend port was baked into the JS bundle at build time.** A `.env` change to `APP_PORT` without `docker compose up --build` left the frontend image with the old port, with no visible sign of why. Fixed to match the pattern the hostname already used (runtime, not build-time): `public/config.js` is a placeholder, `docker-entrypoint.sh` replaces it from the `API_PORT` env var at container *start* (not image build), and `api.js` reads `window.__RUNTIME_CONFIG__` first, with `VITE_API_PORT`/a hardcoded fallback for local development without Docker.
- **`HealthBadge.jsx` — no way to retry after a failure.** The error state was missing the `onClick={refresh}` the healthy state already had. Added.

**Known risks / weaknesses:**
- My first attempt at the CORS fix (an `@app.exception_handler(Exception)` decorator) was wrong — it didn't fix the problem, it just moved it. The bug was caught because I wrote a test that actually reproduced the scenario (a dependency raising an unexpected exception, with an `Origin` header set), instead of just trusting the code "looked right". Worth remembering for the exam as a concrete example of AI-generated code that looked plausible but was wrong, and how it was caught.
- `LLMUnavailableError` now gives `/api/recommend`/`/api/components/extract` a fast, correct fallback instead of a long hanging timeout attempt — but the timeout value itself (`OLLAMA_REQUEST_TIMEOUT_S`, default 60s) is still long. If Ollama hangs (rather than being outright down), the first attempt will still wait up to 60 seconds before the fallback kicks in. Not fixed here — a shorter timeout for the request itself (separate from model-generation time) could be considered if it becomes a problem in practice.

**Tests covering it:**
- `test_llm_parsing.py`: `LLMUnavailableError` gives an immediate fallback without using an extra attempt.
- `test_llm_client.py`, `test_search_client.py` (new files): `OllamaClient`/`SearxngClient`'s own `httpx` error handling, mocked (never a real Ollama/SearXNG).
- `test_api_llm_endpoints.py`: `/search` returns 503 on an unreachable SearXNG; `/extract` returns 422 on an unreachable Ollama; a dedicated test proves that an unexpected, uncaught exception in a dependency still produces a response with an `access-control-allow-origin` header.
- `test_api.py`: `/api/health` exposes `enable_web_lookup`.
- `ruff check`/`ruff format --check`/`pytest --cov` green: 147 tests, 95% overall coverage (up from 92%).
- Frontend: `npm run build` and `npm ci` (a clean install from the lockfile) run without errors. All fixes verified manually in a real browser against a real, running local backend (SQLite, no Docker) — including that the `enable_web_lookup`-driven button display actually matches the backend's response, that the `config.js` runtime substitution works (simulated with `sed`, the way `docker-entrypoint.sh` would do it), and that the backup flow still works unchanged with the new global busy-lock. No errors in the browser console.

**Review (filled in by the student):**

## 2026-10-19 – Phase 5: Frontend + polish

**Generated:**
- `frontend/`: a minimal React 18 + Vite app, plain JavaScript/JSX (not TypeScript — judged proportionate, since the frontend is secondary per SPEC §1.1). Three tabs: **Inventory** (list + two ways to add components: web search → pick candidate → extract → confirm flow from §5, plus a manual/advanced JSON form), **Recommend** (free text → `/api/recommend`, shows builds/warnings/`llm_used` status), **Backup** (active backend+destination, "create backup now", list with a "restore" button).
- `frontend/src/api.js`: all backend calls in one place. The backend URL is derived from `window.location.hostname` + a port (originally `VITE_API_PORT`, baked in at build time via a Docker build-arg — **see the fix in the code-review entry above**: the port is now resolved at container start instead) — no hardcoded server IP anywhere, so the frontend works regardless of which address the user accesses the home server on.
- `frontend/Dockerfile`: multi-step build (`npm run build`) served via `vite preview` — **not** `vite dev`, see Assumptions.
- `docker-compose.yml`: a new `frontend` service (port `FRONTEND_PORT`, default 4173).
- `backend/app/main.py`: added `CORSMiddleware` (`allow_origins=["*"]`) — required, since the frontend and backend now run cross-origin from the browser's perspective.
- `docs/architecture.md` (new, required by SPEC §11 for this phase): a services overview with a mermaid diagram, the two main flows (add a component, recommend a build), and §9.3's security section (all AI inference runs locally, only inventory snapshots go to Azure, prompt-injection defenses, CORS rationale).
- `README.md`: updated with the frontend URL and `npm run dev` instructions.

**Assumptions:**
- **The Docker deployment serves a production build (`vite preview`), not `vite dev --host`.** While developing this phase, `npm audit` found a known, moderate vulnerability in esbuild/Vite's dev server (GHSA-67mh-4wv8-2f99: any website can send requests to an exposed dev server and read the response) — relevant because the home-server deployment exposes the port on the network, not just on localhost. `vite preview` serves the static build without the dev server's vulnerable endpoints, so it was chosen instead. `npm run dev` is still scripted for local development (localhost-only, normal use of a dev server).
- **No "edit component" UI.** The backend's `PUT /api/components/{id}` is already built and tested (Phase 1), but the frontend only exposes create/delete — judged sufficient for a 5-minute demo; delete-and-recreate covers the need in practice.
- **Manual component addition uses a raw JSON text box for specs**, not 8 category-specific forms. A full dynamic form per category was judged as too much UI work for a "secondary" frontend; the web-search flow is the intended main path (explicitly requested during requirements clarification), and the JSON box is a fallback for advanced users or when web search is disabled.
- **CORS allows all origins.** Justified and documented in `docs/architecture.md` — a deliberate simplification for a LAN deployment without fixed client addresses, not suitable for a publicly exposed service.
- **The health badge distinguishes between "can't reach the backend at all" and "backend is running, but degraded"** (e.g. Ollama down) — verified manually (see Tests).

**Known risks / weaknesses:**
- **No automated frontend tests.** The spec doesn't require it for the frontend (secondary), and a test setup (Vitest/React Testing Library) hasn't been added in this phase — all verification is manual (see below).
- **`docker compose up` with the new `frontend` service hasn't been run** (same caveat as previous phases), still unverified after the later rebuild to runtime port resolution (`docker-entrypoint.sh`) — only simulated locally with `sed`, never a real container startup. (The original assumption here — that the `VITE_API_PORT` build-arg was only YAML-validated — is outdated: that mechanism has since been removed, see the code-review entry above.)
- **No loading skeletons or optimistic updates** — the UI shows raw error messages from `fetch` (e.g. "Failed to fetch"), which is fine for a demo but not polished for a real user.

**Tests covering it (manual verification, since this is frontend UI):**
- `npm run build` runs without errors; `npm audit` surfaced and justified the choice of `vite preview` over `vite dev` in Docker (see Assumptions).
- The app opened in a real browser (Claude in Chrome) with no backend running: all three tabs render correctly, show error messages instead of crashing, no errors in the browser console.
- The app reopened against a **real, running backend** (local `uvicorn` + SQLite, no Docker): the Inventory tab correctly showed all 27 seeded components; the Backup tab created and listed a real backup (name, timestamp, count, size) — confirming CORS, request/response formats, and the whole backup flow work end-to-end from the browser. The health badge correctly switched from "Backend unreachable" to "Degraded" (Ollama unavailable, DB and storage ok), as expected without a running Ollama.
- The delete button was **not** tested in the browser (triggers `window.confirm`, which would block automation) — the DELETE endpoint is already covered by `test_api.py` on the backend side.
- `ruff check`/`ruff format --check`/`pytest --cov` on the backend still green after the CORS addition (135 tests, 93% overall coverage — unchanged from Phase 4, since the change is wiring only).

**Review (filled in by the student):**

## 2026-10-19 – Phase 4: Azure/local backup

**Generated:**
- `backend/app/config.py`: `backup_backend: Literal["local","azure"]` with case-insensitive normalization (`field_validator(mode="before")`) and a `model_validator(mode="after")` that **fails at Settings construction** (i.e. as early as possible — already when `app.db` is imported, since `db.py` calls `get_settings()` at module load) if `BACKUP_BACKEND=azure` is set without `AZURE_STORAGE_CONNECTION_STRING` or `AZURE_STORAGE_ACCOUNT_URL`. No silent fallback to local storage.
- `backend/app/storage/`: `base.py` (`BackupInfo`, `BackupStorage` protocol), `local.py` (`LocalStorage` — real filesystem I/O, used in all tests via `tmp_path`), `azure_blob.py` (`AzureBlobStorage`, auth via connection string or `DefaultAzureCredential`, creates the container if missing, normalizes "blob doesn't exist" to `FileNotFoundError` so the services layer doesn't need to know about Azure-specific exceptions), `__init__.py` (`get_backup_storage(settings)` — the **only** place that reads `backup_backend`, plus a cached FastAPI dependency).
- `backend/app/services/backup.py`: `export_snapshot` (builds the snapshot JSON from §7.1 via the existing `ComponentRead` serialization — reuses the validation logic instead of duplicating it), `create_backup`, `list_backups` (enriches the storage layer's raw list with `component_count` by downloading and parsing each snapshot — see Assumptions), `restore_backup` (schema_version → component_count sanity check → sha256 → validate every component with Pydantic **before** touching the database at all → delete and reinsert in a single transaction with rollback on an unexpected DB error).
- `backend/app/routers/backup.py`: `POST/GET /api/backup`, `POST /api/backup/restore` (manual `confirm` check → 400, not a Pydantic 422, so it matches SPEC §9.1's test requirement literally).
- `GET /api/health` now also shows `storage` status (calls `storage.list()`), `backup_backend`, and `backup_destination` (container name or directory — never a connection string).
- `.env.example`, `docker-compose.yml` (the backend now gets `BACKUP_BACKEND`/`LOCAL_BACKUP_DIR`/`AZURE_*` env vars plus a `./backups:/app/backups` volume), `README.md` (new section on switching backends).

**Assumptions:**
- **`list_backups()` downloads and parses every backup file to find `component_count`**, rather than requiring it of `BackupStorage.list()` itself — that would have required either an Azure-specific `metadata` parameter on `upload()` (a break from the spec'd Protocol signature) or encoding the count in the filename (conflicting with the exact, spec'd filename format `inventory-<UTC-timestamp>.json`). For a personal project with a handful of backups, the download-per-list-call is acceptable; worth revisiting if the number of backups grows large.
- **`BackupInfo.component_count` is `None` until the service layer fills it in** — the storage layer can't know it cheaply (Azure blob metadata without downloading, a local file without parsing), so the type is deliberately optional instead of forcing a guess.
- **Restore validates *all* components before touching the database at all** — "rollback on failure" therefore mainly covers unexpected DB errors during the actual delete-and-reinsert transaction (tested with a simulated `commit()` failure), not an invalid component (that's caught earlier and never reaches the database).
- **`restore_backup` additionally checks that `component_count` matches the actual number of components** in the file — not an explicit SPEC requirement, but a free, cheap sanity check against corrupted files, consistent with the project's focus on quality assurance.
- **`AzureBlobStorage`'s `download()` normalizes Azure's `ResourceNotFoundError` to `FileNotFoundError`**, so `services/backup.py` can handle "backup doesn't exist" the same way for both backends without importing Azure-specific exceptions.
- **`APP_VERSION` in the snapshot format is a hardcoded constant** (`"0.1.0"`, matching `pyproject.toml`) — not read dynamically from package metadata, since that would require an extra dependency for a one-line purpose.

**Known risks / weaknesses:**
- **The Azure path is tested exclusively with a mocked `BlobServiceClient`** (no Azure account yet, as in earlier phases). When you create an account, you should at minimum run a real backup → list → restore cycle and confirm that `GET /api/health`/`GET /api/backup` show `"azure"` and the container name without leaking the connection string (tested here only with a mocked storage dependency, not an actual Azure connection running through the whole stack).
- **`docker compose up` still hasn't been run in this session** — the `./backups:/app/backups` volume and `BACKUP_BACKEND` env flow-through are only validated by parsing `docker-compose.yml` as YAML, not by actually starting it.
- **No auto-backup** (§7.3's optional "backup after N changes or via a cron endpoint") has been implemented — judged as genuinely optional ("optional" in the spec) and left out to keep the phase focused; `POST /api/backup` can already be called manually from a cron job on the server if that becomes relevant.
- **`routers/backup.py` lines 16 and 52-53 and `main.py`'s error branches aren't covered** — minor, symmetrical error-handling branches identical in pattern to already-tested branches elsewhere.

**Tests covering it:**
- `test_config.py` (6 tests): default `local`, case-insensitive normalization, invalid value rejected, `azure` without credentials fails (regex-matches the exact error message), `azure` with connection string and account URL respectively accepted.
- `test_storage.py` (7 tests — previously incorrectly stated as 8): the factory returns `LocalStorage`/`AzureBlobStorage` correctly (the Azure client mocked for both the connection-string and account-url paths), container creation tolerates `ResourceExistsError`, `LocalStorage` roundtrip, missing file → `FileNotFoundError`, irrelevant files ignored by `list()`.
- `test_backup.py` (15 tests — previously incorrectly stated as 19): a full roundtrip (backup → simulated data loss → restore → identical inventory), tampered hash rejected, unknown `schema_version` rejected, `component_count` mismatch rejected, invalid JSON rejected, invalid component rejected without changing the database, unknown backup name → `FileNotFoundError`/404, unexpected DB error during restore → rollback (verified the original data is still there), `list_backups` handles an unreadable backup file without crashing, and the full API cycle (create → backup → new component → restore → only the original components exist).
- `test_api.py`: `/api/health` never leaks `AZURE_STORAGE_CONNECTION_STRING`, even when Azure is the active backend.
- `ruff check`/`ruff format --check` green. `pytest --cov`: 93% overall; 100% on `services/backup.py` (§9.1 requires ≥80% here), `storage/base.py`, and `storage/local.py`.

**Review (filled in by the student):**

## 2026-10-19 – Phase 3: LLM integration + SearXNG + recommendation pipeline

**Generated:**
- `backend/app/llm/client.py`: `OllamaClient` (httpx against `/api/generate`, structured output via `format=<pydantic JSON schema>`) + an `LLMClient` protocol so tests never hit a real Ollama. `get_llm_client()` is a FastAPI dependency, overridden in all tests.
- `backend/app/llm/prompts.py`: all prompts in one place (requirements interpretation, spec extraction, build ranking). All user-controlled/web-search text is wrapped in `<data label="...">` blocks, and literal `<`/`>` are escaped, so an embedded `</data>` in the input can't "close" the block early — found by my own injection test during development (see Known risks).
- `backend/app/llm/parsing.py`: a generic `call_llm_with_retry()` — invalid JSON/schema → one retry with the error message fed back → fallback. Takes an optional `validate` callback for semantic validation beyond the Pydantic schema (used to reject invented `build_id` values in ranking). `fallback` can be `None` when no meaningful default response exists (see Assumptions about `/extract`).
- `backend/app/search/client.py`: `SearxngClient` against SearXNG's JSON API (requires `format: json` enabled, see `searxng/settings.yml`) + a `SearchClient` protocol for tests.
- `backend/app/schemas/requirements.py` (`ProjectRequirements` + a conservative fallback), `schemas/builds.py` (ranking and API response schemas), `schemas/search.py` (search/extract schemas, including `ExtractedSpecsEnvelope`, which gives the `ComponentSpecs` union a JSON schema to hand to Ollama).
- `backend/app/pipeline/recommend.py`: the 5 steps from SPEC §5 — interpret requirements (LLM) → prefilter (hard minimum requirements: VRAM/RAM/storage/cores) → generate builds (the Phase 2 engine) → rank (LLM, falling back to a deterministic score based on warnings/power draw/form factor) → re-verify the chosen build (defense in depth) → return.
- New endpoints: `POST /api/components/search` (SearXNG candidates, 404 if none found, 400 if `ENABLE_WEB_LOOKUP=false`), `POST /api/components/extract` (a two-step flow: requires a selected `candidate` when web lookup is enabled, goes straight to the LLM's own knowledge when it's disabled; 422 if the LLM output never becomes valid), `POST /api/recommend`.
- `GET /api/health` now also shows `ollama` status (ping against `/api/tags`).
- `docker-compose.yml`: `backend` now also depends on `ollama`/`searxng` (without a healthcheck requirement, since the images don't necessarily have curl/wget); new env variables are passed through. `searxng/settings.yml` (new file) enables JSON output; `SEARXNG_SECRET` is patched in by SearXNG's own image entrypoint.

**Assumptions:**
- **Web search only gives the LLM a title+snippet, not the whole page's HTML.** Fetching and parsing arbitrary web pages was out of scope for this phase — snippet-based extraction is a deliberate simplification, documented here so it can be revisited if it proves insufficient in practice.
- **`/api/components/extract` has no "conservative fallback" instance**, unlike requirements interpretation and ranking. If the LLM never returns valid JSON (after a retry), there's no meaningful default category to guess at — the endpoint returns 422 and asks the user to enter the specs manually, the same philosophy as "no search results" (see below).
- **"No search results" → an error, not an LLM fallback** (the user's explicit choice during requirements clarification): `/search` returns 404 instead of silently falling back to LLM guessing. `ENABLE_WEB_LOOKUP=false` is the only path to pure LLM extraction — an explicit setting, not an implicit fallback on search failure.
- **Hard minimum requirements (min_vram_gb, etc.) treat missing data as "doesn't meet the requirement"** — unlike the compatibility rules (Phase 2), where missing data gives `unknown`. A requirement the user explicitly asked for shouldn't be satisfied by a guess.
- **`required_categories` from the LLM is only used to force the GPU to be a real requirement** when `min_vram_gb` is set (otherwise a GPU-free build could still be chosen even when the user clearly needs VRAM). The rest of the `required_categories` list isn't used for further filtering yet — can be extended if that becomes relevant.
- **`max_builds` also controls how many builds are sent to the LLM for ranking** (`max(max_builds * 3, 10)`, pre-sorted by the deterministic score) — a tradeoff between prompt size and giving the LLM a real choice.
- **The ranking order follows the LLM's response when valid** (validated build_id by build_id); builds the LLM didn't mention but are still valid fill out the rest of `max_builds` by deterministic score.
- **The Ollama service in `docker-compose.yml` has GPU reservation enabled without a healthcheck** — `backend` depends on `service_started`, not `service_healthy`, so startup doesn't block on a slow model load; `/api/health`'s `ollama` field is the real signal.

**Known risks / weaknesses:**
- **Not tested against a real Ollama or SearXNG** (same caveat as previous phases: no Docker on this machine). SPEC §11's acceptance criterion "manual test against Ollama gives a reasonable 'headless local-AI' build" is only verified with `FakeLLMClient` — you should run the real prompt against a running Ollama container on the home server and assess the quality of the response, including whether `qwen2.5:7b-instruct` actually returns valid JSON with Ollama's `format` parameter in practice (structured outputs are model-dependent).
- **SearXNG's JSON format may be blocked by rate limiting/bot protection** on certain upstream search engines, even with `format: json` enabled locally — nothing at the code level can guarantee against this; should be checked manually after deployment.
- **The prompt-injection defense is `<`/`>` escaping, not a full sandbox.** It concretely prevents a malicious component name or web snippet from "closing" the `<data>` block early (found and fixed during test writing, see Assumptions), but a sufficiently well-crafted injection could still try to persuade the model without breaking out of the block — the system's real defense is still that all compatibility is verified by code, and that `specs_verified` is always `false` until the user confirms.
- **The same assumption about flat power-connector lists in `psu_has_gpu_connectors`** (unchanged from Phase 2) still applies and isn't extended here.
- **Coverage gap:** `pipeline/recommend.py` line 63 (RAM hard minimum when data is missing) isn't covered — same pattern as other `unknown` branches, just not explicitly tested. `llm/client.py` and `search/client.py`'s real HTTP calls are untested by design (they require Ollama/SearXNG).

**Tests covering it:**
- `test_llm_parsing.py` (7 tests then, now 8 — the code-review entry above added an `LLMUnavailableError` test): a valid response, invalid JSON → retry, two failures → fallback, an invented `build_id` rejected by the `validate` callback → fallback, a valid `build_id` accepted, and two injection tests that concretely prove an embedded `</data>` gets escaped instead of breaking out of the data block.
- `test_pipeline.py` (12 tests — corrected, previously incorrectly stated as 14): the required "headless local-AI" scenario end-to-end with a fake LLM, incompatible inventory → no builds and no ranking call, LLM failure at both steps → deterministic fallback, hard minimum requirements (VRAM/RAM/storage/cores) in `prefilter_candidates`, a missing GPU match → correct `missing`, and the deterministic scorer's preferences (low power, small form factor).
- `test_api_llm_endpoints.py` (9 tests then, now 12 — the code-review entry above added a 503 test, a 422 test, and the CORS-on-500 test): `/search` (candidates, 404 on an empty result, 400 when disabled), `/extract` (web lookup, direct LLM knowledge when disabled, 400 without a selected candidate, 422 on a persistently invalid LLM response), `/recommend` (one build, empty inventory → `missing`).
- `ruff check`/`ruff format --check` green. `pytest --cov`: 93% overall; 100% on `llm/parsing.py` and `llm/prompts.py`, 99% on `pipeline/recommend.py` (§9.1 requires ≥80% here — met).

**Review (filled in by the student):**

## 2026-10-19 – Phase 2: Compatibility

**Generated:**
- `backend/app/compatibility/types.py`: `CandidateComponent`, `Build`, `RuleResult`, `BuildEvaluation` (with a `warnings` property for `unknown` results), `EngineResult`. A new file relative to SPEC.md's directory structure (which only mentions `rules.py` + `engine.py`) — shared types collected in one place to avoid circular imports and duplication between the two.
- `backend/app/compatibility/rules.py`: all 15 rules from SPEC §6 (the table has 15 rows, including `display_output_available`), each a pure function `(Build) -> RuleResult`. `psu_wattage_sufficient` uses the new configurable `PSU_BASE_WATT_W`/`PSU_SAFETY_MARGIN` settings (added to `config.py` and `.env.example`).
- `backend/app/compatibility/engine.py`: `generate_builds()` combines candidates per category (limited by `top_n`, default 5) and keeps only builds where no rule fails. `missing` reports categories with no candidates at all.
- `backend/tests/fixtures/sample_inventory.py`: a minimal, hand-built, fully compatible baseline (separate from `app/seed.py`, which is large and realistic for demo purposes, not minimal for assertions) + a `with_specs()` helper for making variants.
- `backend/tests/test_rules.py` (56 tests — previously incorrectly stated as 41 here, a simple counting mistake when written, corrected after a later accuracy review of this log) and `backend/tests/test_engine.py` (8 tests).

**Assumptions:**
- **`Build` has exactly one component per category, including `storage`.** SPEC §6's `storage_slots_available` is written to count multiple drives; here, 1 drive is counted against the motherboard's slots/ports. Multi-drive builds are out of scope for now — mentioned explicitly so it can be revisited if it becomes relevant (e.g. for a "headless local-AI" build with multiple drives).
- **`display_output_available` is the only rule with an extra argument (`headless`).** The other 14 rules don't know about the use case (that's Phase 3/the LLM's domain) — `engine.generate_builds()` itself takes a `headless: bool` parameter and only passes it to this one rule.
- **"Not applicable" (e.g. no GPU selected, or an AIO cooler in `cooler_fits_case`) is returned as `pass`,** not a fourth status. SPEC §6 lists only pass/fail/unknown, and "rule doesn't apply" is semantically closer to pass (it doesn't block) than unknown (there isn't missing data, the rule is just irrelevant).
- **Candidate order and the `top_n` limit are the engine caller's responsibility.** The engine takes candidates in the order it receives them and cuts at `top_n` per category — a relevance sort (e.g. "closest to the user's requirements") belongs to the Phase 3 pipeline, where there are actually requirements to sort by.
- **The PSU safety margin/base watt (`PSU_SAFETY_MARGIN=1.3`, `PSU_BASE_WATT_W=75`)** is now an env var, but is only passed to the `backend` container in `docker-compose.yml` — not verified against an actually running container in this session (same caveat as Phase 1 regarding `docker compose up`).

**Known risks / weaknesses:**
- `psu_has_gpu_connectors` compares power connectors with a `Counter` (accounting for a GPU that may require two 8-pin connectors), but assumes the PSU's `pcie_power_connectors` list is a flat list of all available connectors — if two PSUs in practice share a cable run, this is a simplification.
- `cooler_fits_case` only covers air coolers (as SPEC §6 asks for); AIO radiator size against the case's radiator support isn't checked, because `CaseSpecs` (§4.2) has no `max_radiator_mm` field. Worth mentioning at the exam if asked about AIO builds.
- The combinatorics in `generate_builds()` are `O(top_n^7 * (top_n + gpu_count))` in the worst case — with `top_n=5` this is manageable (a few hundred thousand combinations, each evaluation is a cheap comparison), but no actual performance test has been done against a ~200-component inventory, which SPEC §5 mentions as the target. Should be profiled in Phase 3, once the pipeline actually feeds the engine a realistic number of candidates per category.
- `storage_slots_available` checks `>= 1` free slot/port, not whether the slot/port is already "used" by another drive in the same build — relevant only if multi-drive builds are added later (see Assumptions).

**Tests covering it:**
- `backend/tests/test_rules.py`: all 15 rules tested for pass, fail, and unknown; the four rules with a "not applicable" branch (`gpu_fits_case`, `cooler_fits_case`, `psu_has_gpu_connectors`, `display_output_available`) have an extra test for that branch.
- `backend/tests/test_engine.py`: a known-compatible inventory → 1 valid build; incompatible socket → 0 builds; missing category → correct `missing`; headless with no GPU → 1 build; iGPU with no dedicated GPU (both headless and not) → 1 build; no GPU/iGPU and not headless → 0 builds; an `unknown` result shows up as a warning, not a rejection; `top_n` actually limits which candidates are examined.
- `ruff check`/`ruff format --check` green. `pytest --cov`: 100% coverage on `compatibility/rules.py` and `compatibility/engine.py` (SPEC §9.1 requires ≥80% here); 92% overall (the untested lines are still only `bootstrap.py`/`seed.py`, both one-off scripts).

**Review (filled in by the student):**

## 2026-10-19 – Phase 1: Foundation

**Generated:**
- Repo skeleton: `.gitignore`, `.env.example`, `docker-compose.yml` (4 services: `db`, `backend`, `ollama`, `searxng` — only `db`+`backend` are used by code in this phase; `ollama`/`searxng` are included from the start, per an explicit wish for a complete, clone-and-run-ready stack).
- `backend/Dockerfile`, `backend/pyproject.toml` (FastAPI, SQLAlchemy 2.0, Pydantic v2, pydantic-settings, PyMySQL; dev extras: pytest, pytest-cov, httpx, ruff).
- `backend/app/config.py` (pydantic-settings, `DATABASE_URL`), `app/db.py` (engine/session, `get_db`), `app/enums.py` (`Category`, `Condition`, `SpecsSource` as `StrEnum`).
- `backend/app/models.py`: the SQLAlchemy model `Component` with a JSON `specs` column, `CheckConstraint(quantity >= 0)`, enums stored as their `.value` (not SQLAlchemy's default `.name`).
- `backend/app/schemas/components.py`: a discriminated union (`category`) over 8 category specs (cpu/motherboard/ram/gpu/storage/psu/case/cooler) per SPEC §4.2. All specs fields are optional (`None` default), so manual entry with partial knowledge is possible, and the Phase 2 rules can return "unknown" for missing data.
- `backend/app/routers/components.py`: CRUD endpoints (`GET/POST /api/components`, `GET/PUT/DELETE /api/components/{id}`), filtering by `category`. The `category` column is always derived from `specs.category` — no separate, potentially conflicting category input.
- `backend/app/main.py`: `GET /api/health` (checks the DB connection with `SELECT 1`).
- `backend/app/bootstrap.py`: a separate `create_all()` script, run in the Docker entrypoint before `uvicorn` starts — deliberately *not* in FastAPI's lifespan, so importing `app.main` in tests never touches the real database.
- `backend/app/seed.py`: ~25 components (actually 27) — 8 mirror the user's own PC (Ryzen 5 3600, TUF B450M-PLUS, Corsair DDR4-3000 16GB, RTX 2060 6GB, Intel NVMe 1TB + invented PSU/case/air cooler set to match the build), the rest are invented parts for variety. Idempotent (only seeds an empty table). Deliberately includes incompatibility via a realistic mixed inventory (AM4 CPUs + LGA1700 boards, SODIMM RAM for desktop, a `faulty`-marked PSU, a `quantity=0` SSD, an ITX case too small for ATX parts) instead of one artificial example.
- `backend/tests/conftest.py` + `backend/tests/test_api.py`: 14 tests against SQLite in-memory via `TestClient` + a dependency override of `get_db`.
- `docs/exam-requirements.md`: an extract of exam rules from the `notes/` documents (only §2.1/§3.1 from the elective catalog, the whole kickoff slideshow).
- Removed `docs/agents/` (issue tracker/triage labels/domain workflow) per the user's request — following only SPEC.md phases + this log.

**Assumptions:**
- `PUT /api/components/{id}` is implemented as a partial update (only fields sent are updated), not a full replacement — SPEC doesn't specify the semantics.
- Tables are created via `Base.metadata.create_all()`, not Alembic migrations — judged proportionate for an exam project with no need for migration history.
- RAM specs use the stated speed (DDR4-3000) for the user's real RAM, even though Windows reported it running at 2133 MT/s (without XMP) — specs describe the part's capability, not its runtime configuration.
- GPU passthrough to Ollama is enabled by default in compose (not commented out as SPEC §3 otherwise suggests), because the user's actual home-server target has a free GPU. Clearly commented in `docker-compose.yml`, so it can easily be removed on a different host.
- "~25 components" is interpreted as approximate, not exact — ended up at 27.

**Known risks / weaknesses:**
- `docker compose up` has **not** been tested in practice in this session (no Docker on the development machine). Only verified: `backend` imports and runs correctly, tests run green against SQLite. You should run `docker compose up -d --build` on the home server and confirm `db`+`backend` start, migrate, and seed correctly, before Phase 1 is considered done per SPEC §11's criterion.
- The MariaDB healthcheck in `docker-compose.yml` uses `healthcheck.sh` from the official MariaDB image — not verified against a running container in this session.
- The `ollama` service's GPU reservation (`deploy.resources.reservations.devices`) requires the NVIDIA Container Toolkit on the host; fails silently if it isn't installed (Docker will fail to start just that service, not the rest of the stack — should be checked manually).
- No rate limiting / auth on the API — out of scope for a local exam project, but worth mentioning if an examiner asks.
- A `StarletteDeprecationWarning` about `httpx` in the test run (recommending "httpx2") — came from the newest pip-installed versions of FastAPI/Starlette/httpx. Not investigated further; doesn't affect test results.
- The seed data's invented PSU/case/cooler are clearly marked in the `notes` field, but don't represent actually owned hardware — important to be able to explain at the exam if asked about the data basis.

**Tests covering it:**
- `backend/tests/test_api.py` (14 tests): health check, CRUD (create/list/get/update/delete), category filtering, negative quantity → 422, unknown category value → 422, partial specs (missing fields → `None`), category change via `specs` on update, 404 for a missing id on get/update/delete.
- `ruff check` and `ruff format --check` green. `pytest --cov`: 86% overall coverage (the untested lines are `bootstrap.py`/`seed.py`, which are one-off scripts, not business logic — SPEC's 80% requirement applies to `compatibility/`, `llm/parsing.py`, `pipeline/`, `services/backup.py`, which only arrive in later phases).

**Review (filled in by the student):**
