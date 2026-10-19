# AI-udviklingslog

Se SPEC.md §10 for formatet. Hver post dækker én fase/feature. "Review" udfyldes af den studerende.

## 2026-10-19 – Fase 2: Kompatibilitet

**Genereret:**
- `backend/app/compatibility/types.py`: `CandidateComponent`, `Build`, `RuleResult`, `BuildEvaluation` (med `warnings`-property for `unknown`-resultater), `EngineResult`. Ny fil ift. SPEC.md's mappestruktur (som kun nævner `rules.py` + `engine.py`) — delte typer samlet ét sted for at undgå cirkulære imports og duplikering mellem de to.
- `backend/app/compatibility/rules.py`: alle 15 regler fra SPEC §6 (tabellen har 15 rækker, inkl. `display_output_available`), hver som en ren funktion `(Build) -> RuleResult`. `psu_wattage_sufficient` bruger de nye konfigurerbare `PSU_BASE_WATT_W`/`PSU_SAFETY_MARGIN`-settings (tilføjet til `config.py` og `.env.example`).
- `backend/app/compatibility/engine.py`: `generate_builds()` kombinerer kandidater pr. kategori (begrænset af `top_n`, default 5) og beholder kun builds hvor ingen regel fejler. `missing` rapporterer kategorier uden nogen kandidater overhovedet.
- `backend/tests/fixtures/sample_inventory.py`: en minimal, håndlavet, fuldt kompatibel baseline (separat fra `app/seed.py`, som er stort og realistisk til demo, ikke minimalt til assertions) + en `with_specs()`-hjælpefunktion til at lave varianter.
- `backend/tests/test_rules.py` (41 tests) og `backend/tests/test_engine.py` (8 tests).

**Antagelser:**
- **`Build` har præcis én komponent pr. kategori, inkl. `storage`.** SPEC §6's `storage_slots_available` er skrevet til at tælle flere drev; her tælles 1 drev mod bundkortets slots/porte. Multi-drev-builds er ude af scope for nu — nævnt eksplicit, så det kan tages op igen hvis det bliver relevant (fx til "headless lokal-AI" med flere drev).
- **`display_output_available` er den eneste regel med et ekstra argument (`headless`).** De øvrige 14 regler kender ikke til use-casen (det er fase 3/LLM's domæne) — engine.generate_builds() tager selv en `headless: bool`-parameter og videresender den kun til denne ene regel.
- **"Ikke relevant" (fx intet GPU valgt, eller en AIO-køler ved `cooler_fits_case`) returneres som `pass`,** ikke en fjerde status. SPEC §6 lister kun pass/fail/unknown, og "regel gælder ikke" er semantisk tættere på pass (den blokerer ikke) end unknown (der er ikke manglende data, reglen er bare irrelevant).
- **Kandidat-rækkefølge og `top_n`-begrænsning er engine-callerens ansvar.** Engine tager kandidaterne i den orden, de får dem, og skærer ved `top_n` pr. kategori — en relevans-sortering (fx "tættest på brugerens krav") hører til pipeline'en i fase 3, hvor der faktisk er krav at sortere efter.
- **PSU-sikkerhedsmargin/base-watt (`PSU_SAFETY_MARGIN=1.3`, `PSU_BASE_WATT_W=75`)** er nu en env-var, men bliver kun sendt til `backend`-containeren i `docker-compose.yml` — ikke verificeret med en faktisk kørende container i denne session (se samme forbehold som fase 1 om `docker compose up`).

**Kendte risici / svagheder:**
- `psu_has_gpu_connectors` sammenligner strømstik med `Counter` (tager højde for at en GPU kan kræve to 8-pin-stik), men antager at PSU'ens `pcie_power_connectors`-liste er en flad liste af alle tilgængelige stik — hvis to PSU'er i praksis deler en kabel-streng, er dette en forsimpling.
- `cooler_fits_case` dækker kun luftkølere (som SPEC §6 beder om); AIO-radiatorstørrelse mod kabinettets radiator-support tjekkes ikke, fordi `CaseSpecs` (§4.2) ikke har et `max_radiator_mm`-felt. Værd at nævne til eksamen, hvis der spørges ind til AIO-builds.
- Kombinatorikken i `generate_builds()` er `O(top_n^7 * (top_n + gpu_count))` i værste fald — med `top_n=5` er det håndterbart (et par hundredtusind kombinationer, hver evaluering er billige sammenligninger), men der er ikke lavet et faktisk ydelsestjek mod et ~200-komponent-lager, som SPEC §5 nævner som målet. Bør profileres i fase 3, når pipeline'en faktisk fodrer engine'en med et realistisk antal kandidater pr. kategori.
- `storage_slots_available` tjekker `>= 1` ledig slot/port, ikke om slottet/porten allerede er "brugt" af et andet drev i samme build — relevant kun hvis multi-drev-builds tilføjes senere (se Antagelser).

**Tests der dækker det:**
- `backend/tests/test_rules.py`: alle 15 regler testet for pass, fail og unknown; de fire regler med en "ikke relevant"-gren (`gpu_fits_case`, `cooler_fits_case`, `psu_has_gpu_connectors`, `display_output_available`) har en ekstra test for den gren.
- `backend/tests/test_engine.py`: kendt kompatibelt lager → 1 gyldigt build; inkompatibel socket → 0 builds; manglende kategori → korrekt `missing`; headless uden GPU → 1 build; iGPU uden GPU (både headless og ikke-headless) → 1 build; intet GPU/iGPU og ikke-headless → 0 builds; `unknown`-resultat optræder som warning, ikke afvisning; `top_n` begrænser faktisk hvilke kandidater der undersøges.
- `ruff check`/`ruff format --check` grønne. `pytest --cov`: 100 % dækning på `compatibility/rules.py` og `compatibility/engine.py` (SPEC §9.1 kræver ≥80 % her); 92 % samlet (de utestede linjer er stadig kun `bootstrap.py`/`seed.py`, begge engangsscripts).

**Review (udfyldes af den studerende):**

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
