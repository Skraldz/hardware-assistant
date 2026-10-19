# AI-udviklingslog

Se SPEC.md §10 for formatet. Hver post dækker én fase/feature. "Review" udfyldes af den studerende.

## 2026-10-19 – Fase 3: LLM-integration + SearXNG + anbefalingspipeline

**Genereret:**
- `backend/app/llm/client.py`: `OllamaClient` (httpx mod `/api/generate`, structured output via `format=<pydantic JSON-schema>`) + `LLMClient`-protokol så tests aldrig rammer en rigtig Ollama. `get_llm_client()` er en FastAPI-dependency, overrides i alle tests.
- `backend/app/llm/prompts.py`: alle prompts samlet ét sted (krav-fortolkning, spec-udtræk, build-rangering). Al brugerstyret/websøgnings-tekst pakkes i `<data label="...">`-blokke, og literal `<`/`>` escapes, så en indlejret `</data>` i inputtet ikke kan "lukke" blokken for tidligt — fundet af min egen injection-test under udvikling (se Kendte risici).
- `backend/app/llm/parsing.py`: generisk `call_llm_with_retry()` — ugyldig JSON/skema → én retry med fejlbesked → fallback. Tager en valgfri `validate`-callback til semantisk validering ud over Pydantic-skemaet (bruges til at afvise opfundne `build_id`'er i rangeringen). `fallback` kan være `None`, når der ikke findes et meningsfuldt standardsvar (se Antagelser om `/extract`).
- `backend/app/search/client.py`: `SearxngClient` mod SearXNG's JSON-API (kræver `format: json` aktiveret, se `searxng/settings.yml`) + `SearchClient`-protokol til tests.
- `backend/app/schemas/requirements.py` (`ProjectRequirements` + konservativ fallback), `schemas/builds.py` (rangerings- og API-svarskemaer), `schemas/search.py` (søg/udtræk-skemaer, inkl. `ExtractedSpecsEnvelope` der giver `ComponentSpecs`-unionen et JSON-skema at give til Ollama).
- `backend/app/pipeline/recommend.py`: de 5 trin fra SPEC §5 — fortolk krav (LLM) → forfiltrér (hårde minimumskrav: VRAM/RAM/lager/kerner) → generér builds (fase 2-motoren) → rangér (LLM, med fallback til en deterministisk score baseret på advarsler/effektforbrug/formfaktor) → gen-verificér det valgte build (forsvar i dybden) → returnér.
- Nye endpoints: `POST /api/components/search` (SearXNG-kandidater, 404 hvis ingen findes, 400 hvis `ENABLE_WEB_LOOKUP=false`), `POST /api/components/extract` (to-trins flow: kræver et valgt `candidate` når websøgning er aktiveret, går direkte på LLM'ens egen viden når den er slået fra; 422 hvis LLM-output aldrig bliver gyldigt), `POST /api/recommend`.
- `GET /api/health` viser nu også `ollama`-status (ping mod `/api/tags`).
- `docker-compose.yml`: `backend` afhænger nu også af `ollama`/`searxng` (uden healthcheck-krav, da billederne ikke nødvendigvis har curl/wget); nye env-variabler videresendes. `searxng/settings.yml` (ny fil) aktiverer JSON-output; `SEARXNG_SECRET` patches ind af SearXNG-imagets egen entrypoint.

**Antagelser:**
- **Websøgning giver kun titel+snippet til LLM'en, ikke hele sidens HTML.** At hente og parse arbitrære websider var ude af scope for denne fase — snippet-baseret udtræk er en bevidst forenkling, dokumenteret her så den kan genbesøges, hvis det viser sig utilstrækkeligt i praksis.
- **`/api/components/extract` har ingen "konservativ fallback"-instans**, i modsætning til krav-fortolkning og rangering. Hvis LLM'en aldrig returnerer gyldigt JSON (efter retry), er der ingen meningsfuld standard-kategori at gætte på — endepunktet returnerer 422 og beder brugeren indtaste specifikationerne manuelt, samme filosofi som "ingen søgeresultater" (se nedenfor).
- **"Ingen søgeresultater" → fejl, ikke LLM-fallback** (brugerens eksplicitte valg under kravafklaringen): `/search` returnerer 404 i stedet for stille at falde tilbage til LLM-gæt. `ENABLE_WEB_LOOKUP=false` er den eneste vej til ren LLM-udtræk — en udtrykkelig indstilling, ikke en implicit fallback ved søgefejl.
- **Hårde minimumskrav (min_vram_gb osv.) behandler manglende data som "opfylder ikke kravet"** — modsat kompatibilitetsreglerne (fase 2), hvor manglende data giver `unknown`. Et krav brugeren eksplicit har bedt om bør ikke opfyldes af et gæt.
- **`required_categories` fra LLM'en bruges kun til at tvinge GPU til at være et reelt krav**, når `min_vram_gb` er sat (ellers ville en GPU-fri løsning stadig kunne vælges, selv når brugeren tydeligvis har brug for VRAM). Resten af `required_categories`-listen er ikke brugt til yderligere filtrering endnu — kan udvides, hvis det bliver relevant.
- **`max_builds` styrer også hvor mange builds, der sendes til LLM'en til rangering** (`max(max_builds * 3, 10)`, forhåndssorteret efter den deterministiske score) — en afvejning mellem prompt-størrelse og at give LLM'en et reelt valg.
- **Rangerings-rækkefølgen følger LLM'ens svar, når det er gyldigt** (valideret build_id for build_id); builds LLM'en ikke nævnte, men som stadig er gyldige, fylder resten af `max_builds` op efter deterministisk score.
- **Ollama-service i `docker-compose.yml` har GPU-reservation slået til uden healthcheck** — `backend` afhænger af `service_started`, ikke `service_healthy`, så opstart blokerer ikke på en langsom modelindlæsning; `/api/health`'s `ollama`-felt er det reelle signal.

**Kendte risici / svagheder:**
- **Ikke testet mod en rigtig Ollama eller SearXNG** (samme forbehold som tidligere faser: intet Docker på denne maskine). SPEC §11's accept-kriterium "manuel test mod Ollama giver et fornuftigt 'headless lokal-AI'-build" er kun verificeret med `FakeLLMClient` — du bør køre den rigtige prompt mod en kørende Ollama-container på home-serveren og vurdere kvaliteten af svaret, inkl. om `qwen2.5:7b-instruct` rent faktisk returnerer gyldig JSON med Ollamas `format`-parameter i praksis (strukturerede outputs er modelafhængige).
- **SearXNG's JSON-format kan være blokeret af rate-limiting/botbeskyttelse** på visse opstrøms-søgemotorer, selv med `format: json` aktiveret lokalt — ikke noget kodeniveau kan garantere; bør tjekkes manuelt efter deployment.
- **Prompt-injection-forsvaret er escaping af `<`/`>`, ikke en fuld sandkasse.** Det forhindrer konkret at et ondsindet komponentnavn eller websnippet kan "lukke" `<data>`-blokken tidligt (fundet og fixet under test-skrivning, se Antagelser), men en tilstrækkeligt velformuleret injektion kan stadig forsøge at overtale modellen uden at bryde ud af blokken — systemets egentlige forsvar er stadig at al kompatibilitet verificeres af kode, og at `specs_verified` altid er `false`, indtil brugeren bekræfter.
- **`psu_has_gpu_connectors`-typen antagelse om flade strømstik-lister gælder stadig** (uændret fra fase 2) og er ikke udvidet her.
- **Coverage-gab:** `pipeline/recommend.py` linje 63 (RAM-hård-minimum når data mangler) er ikke dækket — samme mønster som andre `unknown`-grene, blot ikke eksplicit testet. `llm/client.py` og `search/client.py`'s rigtige HTTP-kald er utestede per design (kræver Ollama/SearXNG).

**Tests der dækker det:**
- `test_llm_parsing.py` (7 tests): gyldigt svar, ugyldig JSON → retry, to fejl → fallback, opfundet `build_id` afvist af `validate`-callback → fallback, gyldigt `build_id` accepteret, og to injection-tests der konkret beviser at en indlejret `</data>` bliver escaped i stedet for at bryde ud af data-blokken.
- `test_pipeline.py` (14 tests): den krævede "headless lokal-AI"-scenarie end-to-end med fake LLM, inkompatibelt lager → ingen builds og intet rangerings-kald, LLM-fejl på begge trin → deterministisk fallback, hårde minimumskrav (VRAM/RAM/lager/kerner) i `prefilter_candidates`, manglende GPU-match → korrekt `missing`, og den deterministiske scorers præferencer (lav effekt, lille formfaktor).
- `test_api_llm_endpoints.py` (9 tests): `/search` (kandidater, 404 ved tomt resultat, 400 når slået fra), `/extract` (web-lookup, direkte LLM-viden når slået fra, 400 uden valgt candidate, 422 ved varigt ugyldigt LLM-svar), `/recommend` (et build, tom-lager → `missing`).
- `ruff check`/`ruff format --check` grønne. `pytest --cov`: 93 % samlet; 100 % på `llm/parsing.py` og `llm/prompts.py`, 99 % på `pipeline/recommend.py` (§9.1 kræver ≥80 % her — opfyldt).

**Review (udfyldes af den studerende):**

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
