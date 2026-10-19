# AI-udviklingslog

Se SPEC.md §10 for formatet. Hver post dækker én fase/feature. "Review" udfyldes af den studerende.

## 2026-10-19 – Fase 1: Fundament

**Genereret:**
- Repo-skelet: `.gitignore`, `.env.example`, `docker-compose.yml` (4 services: `db`, `backend`, `ollama`, `searxng` — kun `db`+`backend` bruges af kode i denne fase; `ollama`/`searxng` er med fra start efter eksplicit ønske om en komplet, klon-og-kør-klar stack).
- `backend/Dockerfile`, `backend/pyproject.toml` (FastAPI, SQLAlchemy 2.0, Pydantic v2, pydantic-settings, PyMySQL; dev-ekstras: pytest, pytest-cov, httpx, ruff).
- `backend/app/config.py` (pydantic-settings, `DATABASE_URL`), `app/db.py` (engine/session, `get_db`), `app/enums.py` (`Category`, `Condition`, `SpecsSource` som `StrEnum`).
- `backend/app/models.py`: SQLAlchemy-model `Component` med JSON `specs`-kolonne, `CheckConstraint(quantity >= 0)`, enums lagret som deres `.value` (ikke SQLAlchemys default `.name`).
- `backend/app/schemas/components.py`: discriminated union (`category`) over 8 kategori-specs (cpu/motherboard/ram/gpu/storage/psu/case/cooler) efter SPEC §4.2. Alle specs-felter er optional (`None`-default), så manuel indtastning med delvis viden er mulig, og reglerne i fase 2 kan returnere "unknown" ved manglende data.
- `backend/app/routers/components.py`: CRUD-endpoints (`GET/POST /api/components`, `GET/PUT/DELETE /api/components/{id}`), filtrering på `category`. `category`-kolonnen afledes altid af `specs.category` — ingen separat, potentielt modstridende category-input.
- `backend/app/main.py`: `GET /api/health` (tjekker DB-forbindelse med `SELECT 1`).
- `backend/app/bootstrap.py`: separat `create_all()`-script, kørt i Docker-entrypointet før `uvicorn` starter — bevidst *ikke* i FastAPI's lifespan, så import af `app.main` i tests aldrig rører den rigtige database.
- `backend/app/seed.py`: ~25 komponenter (faktisk 27) — 8 mirrorer brugerens egen pc (Ryzen 5 3600, TUF B450M-PLUS, Corsair DDR4-3000 16GB, RTX 2060 6GB, Intel NVMe 1TB + opdigtet PSU/kabinet/airkøler sat til at matche buildet), resten er opdigtede dele for variation. Idempotent (seeder kun en tom tabel). Indeholder bevidst inkompatibilitet via realistisk blandet lager (AM4-CPU'er + LGA1700-boards, SODIMM-RAM til desktop, en `faulty`-markeret PSU, en `quantity=0`-SSD, et ITX-kabinet for småt til ATX-dele) i stedet for ét kunstigt eksempel.
- `backend/tests/conftest.py` + `backend/tests/test_api.py`: 14 tests mod SQLite in-memory via `TestClient` + dependency override af `get_db`.
- `docs/exam-requirements.md`: udtræk af eksamensregler fra `notes/`-dokumenterne (kun §2.1/§3.1 fra valgfagskataloget, hele kickoff-slideshowet).
- Fjernet `docs/agents/` (issue-tracker/triage-labels/domain-workflow) efter brugerens ønske — følger kun SPEC.md-faser + denne log.

**Antagelser:**
- `PUT /api/components/{id}` er implementeret som delvis opdatering (kun felter sendt med opdateres), ikke en fuld erstatning — SPEC specificerer ikke semantikken.
- Tabeller oprettes via `Base.metadata.create_all()`, ikke Alembic-migrationer — vurderet proportionalt for et eksamensprojekt uden behov for migrationshistorik.
- RAM-specs bruger den angivne hastighed (DDR4-3000) for brugerens rigtige RAM, selv om Windows rapporterede den kørende som 2133 MT/s (uden XMP) — specs beskriver delens kapabilitet, ikke runtime-konfiguration.
- GPU-passthrough til Ollama er aktiveret by default i compose (ikke udkommenteret som SPEC §3 ellers foreslår), fordi brugerens faktiske home-server-mål har en fri GPU. Tydeligt kommenteret i `docker-compose.yml`, så det let kan fjernes på en anden host.
- "~25 komponenter" er tolket som cirka, ikke eksakt — endte på 27.

**Kendte risici / svagheder:**
- `docker compose up` er **ikke** testet i praksis i denne session (ingen Docker på udviklingsmaskinen). Kun verificeret: `backend` importerer og kører korrekt, tests kører grønt mod SQLite. Du bør køre `docker compose up -d --build` på home-serveren og bekræfte at `db`+`backend` starter, migrerer og seeder korrekt, før fase 1 regnes som færdig efter SPEC §11's kriterium.
- MariaDB-healthcheck i `docker-compose.yml` bruger `healthcheck.sh` fra det officielle MariaDB-image — ikke verificeret mod en kørende container i denne session.
- `ollama`-servicens GPU-reservation (`deploy.resources.reservations.devices`) kræver NVIDIA Container Toolkit på hosten; fejler stille hvis det ikke er installeret (Docker vil fejle ved opstart af netop den service, ikke resten af stacken — bør tjekkes manuelt).
- Ingen rate limiting / auth på API'et — uden for scope for et lokalt eksamensprojekt, men værd at nævne hvis en eksaminator spørger.
- `StarletteDeprecationWarning` om `httpx` i testkørslen (anbefaler "httpx2") — kom fra de nyeste pip-installerede versioner af FastAPI/Starlette/httpx. Ikke undersøgt yderligere; påvirker ikke testresultater.
- Seed-dataens opdigtede PSU/kabinet/køler er tydeligt markeret i `notes`-feltet, men er ikke retvisende for faktisk ejet hardware — vigtigt at kunne forklare til eksamen hvis spurgt om datagrundlaget.

**Tests der dækker det:**
- `backend/tests/test_api.py` (14 tests): health-check, CRUD (create/list/get/update/delete), kategori-filtrering, negativ quantity → 422, ukendt category-værdi → 422, delvis specs (manglende felter → `None`), kategoriskift via `specs` ved update, 404 for manglende id ved get/update/delete.
- `ruff check` og `ruff format --check` grønne. `pytest --cov`: 86 % samlet dækning (de utestede linjer er `bootstrap.py`/`seed.py`, som er engangsscripts, ikke forretningslogik — SPEC's 80 %-krav gælder `compatibility/`, `llm/parsing.py`, `pipeline/`, `services/backup.py`, som først kommer i senere faser).

**Review (udfyldes af den studerende):**
