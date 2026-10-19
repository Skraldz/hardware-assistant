# AI-udviklingslog

Se SPEC.md §10 for formatet. Hver post dækker én fase/feature. "Review" udfyldes af den studerende.

## 2026-10-19 – Code review (/code-review) + rettelser

Kørt efter fase 5. Et multi-agent code-review fandt 10 bekræftede fund på tværs af frontend og backend; alle er rettet i denne post.

**Genereret/rettet:**
- **`InventoryView.jsx` — "Udtræk direkte"-knappen var død ved standardkonfiguration.** Backend kræver et `candidate`, når `ENABLE_WEB_LOOKUP=true` (standard), men knappen kaldte altid `extractComponent(navn, null)`. Rettet ved at udvide det mønster, `HealthBadge`/`BackupView` allerede brugte (vise hvad backend rapporterer, aldrig antage): `/api/health` eksponerer nu `enable_web_lookup`, og `InventoryView` henter det og viser **enten** "Søg"-knappen (når slået til) **eller** en direkte udtræk-knap (når slået fra) — aldrig en knap, der er garanteret at fejle.
- **`InventoryView.jsx` — navn/specs kunne blive usynkroniseret.** `handleConfirmSave` læste det *aktuelle* `searchName`-state i stedet for navnet på udtræks-tidspunktet, og søgefeltet var ikke låst under gennemgang. Rettet: navnet fryses i et separat `confirmName`-state ved udtræk, og inputfeltet deaktiveres, mens et resultat er til gennemgang.
- **`InventoryView.jsx` — kapløb mellem samtidige søge/udtræk-kald.** Et langsommere, allerede overhalet kald kunne overskrive et nyere resultat, når det endelig blev færdigt. Rettet med en simpel request-sekvens-tæller (`useRef`), der ignorerer svar fra et kald, der er blevet overhalet af et nyere.
- **`InventoryView.jsx` — manuel tilføjelse kunne stille og roligt droppe felter.** `category`-dropdownet overskrev altid specs-JSON'ens `category`, og da ingen spec-model har `extra="forbid"`, forsvandt felter fra en forkert kategori uden varsel. Rettet: hvis JSON'ens `category` findes og er forskellig fra dropdownet, vises en fejl i stedet for at overskrive stille.
- **`backend/app/main.py` — 500-fejl manglede CORS-headers.** `@app.exception_handler(Exception)` virkede ikke som ventet: FastAPI flytter specifikt en handler registreret på selve `Exception`-typen til `ServerErrorMiddleware`, som Starlette altid placerer **uden for** brugerdefineret middleware (inkl. `CORSMiddleware`) — fundet ved at min første rettelse fejlede i en test, der direkte eftergjorde fejlscenariet (se Kendte risici). Den korrekte løsning er en almindelig `BaseHTTPMiddleware`, tilføjet *før* `CORSMiddleware` (så den ender inden for CORS i kaldstakken), som selv fanger exceptions og returnerer et normalt `Response`-objekt. Samtidig er `OllamaClient`/`SearxngClient`s `httpx`-kald nu pakket ind og rejser `LLMUnavailableError`/`SearchUnavailableError` i stedet for at lække rå `httpx`-exceptions — `call_llm_with_retry` går nu direkte til fallback ved en utilgængelig Ollama (uden at spilde retry-forsøg på en fejl, der ikke retter sig selv), og `/api/components/search` returnerer en ren 503 ved utilgængelig SearXNG.
- **`BackupView.jsx` — samtidige destruktive handlinger var ikke forhindret.** `disabled`-tjekket dækkede kun rækken i gang; andre "Gendan"-knapper og "Lav backup nu" var stadig klikbare under en igangværende gendannelse. Rettet med én global `activeAction`-tilstand, der låser alle handlingsknapper, mens én er i gang.
- **`api.js` — fejlbeskeder blev vist med overflødige anførselstegn.** `JSON.stringify(detail)` blev brugt uanset om `detail` allerede var en almindelig streng (hvilket de fleste backend-fejl er). Rettet til kun at stringify'e, når `detail` ikke allerede er en streng.
- **`frontend/Dockerfile` — buildet brugte ikke den committede lockfile.** `npm install` kørte før `package-lock.json` overhovedet var kopieret ind. Rettet: kopiér begge filer sammen og brug `npm ci`.
- **`docker-compose.yml`/`Dockerfile` — backend-porten blev bagt ind i JS-bundlet ved build-tid.** En `.env`-ændring af `APP_PORT` uden `docker compose up --build` efterlod frontend-imaget med den gamle port, uden noget synligt tegn på hvorfor. Rettet til at matche det mønster, hostname'et allerede brugte (runtime, ikke build-time): `public/config.js` er en placeholder, `docker-entrypoint.sh` erstatter den fra `API_PORT`-env'en ved container-*start* (ikke image-build), og `api.js` læser `window.__RUNTIME_CONFIG__` først, med `VITE_API_PORT`/et hardcodet fallback for lokal udvikling uden Docker.
- **`HealthBadge.jsx` — ingen måde at prøve igen på efter en fejl.** Fejltilstanden manglede den `onClick={refresh}`, den sunde tilstand allerede havde. Tilføjet.

**Kendte risici / svagheder:**
- Min første forsøg på CORS-fixet (en `@app.exception_handler(Exception)`-dekorator) var forkert — det løste ikke problemet, det bare flyttede det. Fejlen blev fanget, fordi jeg skrev en test, der faktisk eftergjorde scenariet (en afhængighed, der rejser en uventet exception, med et `Origin`-header sat), i stedet for kun at stole på at koden "så rigtig ud". Værd at huske til eksamen som et konkret eksempel på AI-genereret kode, der så plausibel ud, men var forkert, og hvordan det blev fanget.
- `LLMUnavailableError` giver nu `/api/recommend`/`/api/components/extract` en hurtig, korrekt fallback i stedet for et langt hængende timeout-forsøg — men selve timeout-værdien (`OLLAMA_REQUEST_TIMEOUT_S`, default 60s) er stadig lang. Hvis Ollama hænger (i stedet for decideret er nede), vil det første forsøg stadig vente op til 60 sekunder, før fallback aktiveres. Ikke rettet her — en kortere timeout for selve anmodningen (adskilt fra modelgenereringstid) kunne overvejes, hvis det bliver et problem i praksis.

**Tests der dækker det:**
- `test_llm_parsing.py`: `LLMUnavailableError` giver øjeblikkelig fallback uden at bruge et ekstra forsøg.
- `test_llm_client.py`, `test_search_client.py` (nye filer): `OllamaClient`/`SearxngClient`s egne `httpx`-fejlhåndtering, mocket (aldrig en rigtig Ollama/SearXNG).
- `test_api_llm_endpoints.py`: `/search` returnerer 503 ved utilgængelig SearXNG; `/extract` returnerer 422 ved utilgængelig Ollama; en dedikeret test beviser at et uventet, ufanget exception i en afhængighed stadig giver et svar med `access-control-allow-origin`-header.
- `test_api.py`: `/api/health` eksponerer `enable_web_lookup`.
- `ruff check`/`ruff format --check`/`pytest --cov` grønne: 147 tests, 95 % samlet dækning (op fra 92 %).
- Frontend: `npm run build` og `npm ci` (ren installation fra lockfile) kørt uden fejl. Alle fixes verificeret manuelt i en rigtig browser mod en rigtig, kørende lokal backend (SQLite, uden Docker) — inkl. at `enable_web_lookup`-styret knapvisning rent faktisk matcher backend's svar, at `config.js`-runtime-substitutionen virker (simuleret med `sed`, som `docker-entrypoint.sh` ville gøre det), og at backup-flowet stadig virker uændret med den nye globale busy-lås. Ingen fejl i browser-konsollen.

**Review (udfyldes af den studerende):**

## 2026-10-19 – Fase 5: Frontend + polish

**Genereret:**
- `frontend/`: minimal React 18 + Vite-app, almindelig JavaScript/JSX (ikke TypeScript — vurderet proportionalt, da frontenden er sekundær per SPEC §1.1). Tre faner: **Lager** (liste + to måder at tilføje komponenter: søg-på-nettet → vælg kandidat → udtræk → bekræft-flowet fra §5, samt en manuel/avanceret JSON-formular), **Anbefaling** (fri tekst → `/api/recommend`, viser builds/advarsler/`llm_used`-status), **Backup** (aktiv backend+destination, "lav backup nu", liste med "gendan"-knap).
- `frontend/src/api.js`: alle backend-kald samlet ét sted. Backend-URL udledes af `window.location.hostname` + en port (oprindeligt `VITE_API_PORT`, bagt ind ved build-tid via Docker build-arg — **se rettelse i code review-posten ovenfor**: porten opløses nu ved container-start i stedet) — ingen hardcodet server-IP noget sted, så frontenden virker uanset hvilken adresse brugeren tilgår home-serveren på.
- `frontend/Dockerfile`: multi-step build (`npm run build`) serveret via `vite preview` — **ikke** `vite dev`, se Antagelser.
- `docker-compose.yml`: ny `frontend`-service (port `FRONTEND_PORT`, default 4173).
- `backend/app/main.py`: tilføjet `CORSMiddleware` (`allow_origins=["*"]`) — krævet, da frontend og backend nu kører cross-origin fra browserens perspektiv.
- `docs/architecture.md` (nyt, krævet af SPEC §11 for denne fase): services-oversigt med et mermaid-diagram, de to hovedflows (tilføj komponent, anbefal build), og §9.3's sikkerhedsafsnit (al AI-inferens kører lokalt, kun inventar-snapshots til Azure, prompt-injection-forsvar, CORS-begrundelse).
- `README.md`: opdateret med frontend-URL og `npm run dev`-instruktion.

**Antagelser:**
- **Docker-deploymentet serverer et produktionsbuild (`vite preview`), ikke `vite dev --host`.** Under udvikling af denne fase fandt `npm audit` en kendt, moderat sårbarhed i esbuild/Vite's dev-server (GHSA-67mh-4wv8-2f99: enhver hjemmeside kan sende requests til en eksponeret dev-server og læse svaret) — relevant, fordi home-server-deploymentet eksponerer porten på netværket, ikke kun på localhost. `vite preview` serverer det statiske build uden dev-serverens sårbare endpoints, så det er valgt i stedet. `npm run dev` er stadig scriptet til lokal udvikling (localhost-only, normal brug af en dev-server).
- **Ingen "rediger komponent"-UI.** Backend'ens `PUT /api/components/{id}` er allerede bygget og testet (fase 1), men frontenden eksponerer kun opret/slet — vurderet tilstrækkeligt til en 5-minutters demo; slet-og-genopret dækker behovet i praksis.
- **Manuel komponent-tilføjelse bruger en rå JSON-tekstboks til specs**, ikke 8 kategori-specifikke formularer. En fuld dynamisk formular pr. kategori blev vurderet som for meget UI-arbejde for en "sekundær" frontend; søg-på-nettet-flowet er den tilsigtede hovedvej (ønsket eksplicit under kravafklaringen), JSON-boksen er faldback for avancerede brugere eller når websøgning er slået fra.
- **CORS tillader alle origins.** Begrundet og dokumenteret i `docs/architecture.md` — en bevidst forenkling for en LAN-deployment uden faste klient-adresser, ikke egnet til en offentligt eksponeret tjeneste.
- **Health-badge'en skelner mellem "kan slet ikke nå backend" og "backend kører, men degraderet"** (fx Ollama nede) — verificeret manuelt (se Tests).

**Kendte risici / svagheder:**
- **Ingen automatiserede frontend-tests.** SPEC stiller ikke krav om det for frontenden (sekundær), og der er ikke tilføjet et testsetup (Vitest/React Testing Library) i denne fase — al verifikation er manuel (se nedenfor).
- **`docker compose up` med den nye `frontend`-service er ikke kørt** (samme forbehold som tidligere faser), stadig uverificeret efter den senere ombygning til runtime-portopløsning (`docker-entrypoint.sh`) — kun simuleret lokalt med `sed`, aldrig en rigtig container-opstart. (Den oprindelige antagelse her — at build-arg'et `VITE_API_PORT` kun var YAML-valideret — er forældet: den mekanisme er siden fjernet, se code review-posten ovenfor.)
- **Ingen loading-skeletons eller optimistiske opdateringer** — UI'en viser rå fejlbeskeder fra `fetch` (fx "Failed to fetch"), hvilket er fint til en demo, men ikke poleret til en rigtig bruger.

**Tests der dækker det (manuel verifikation, da dette er frontend-UI):**
- `npm run build` kører uden fejl; `npm audit` afdækkede og begrundede valget af `vite preview` frem for `vite dev` i Docker (se Antagelser).
- Appen åbnet i en rigtig browser (Claude i Chrome) uden kørende backend: alle tre faner renderer korrekt, viser fejlbeskeder i stedet for at crashe, ingen fejl i browser-konsollen.
- Appen genåbnet mod en **rigtig, kørende backend** (lokal `uvicorn` + SQLite, uden Docker): Lager-fanen viste alle 27 seedede komponenter korrekt; Backup-fanen oprettede og listede en rigtig backup (navn, tidspunkt, antal, størrelse) — bekræfter CORS, request/response-formater og hele backup-flowet virker end-to-end fra browseren. Health-badgen skiftede korrekt fra "Backend uanselig" til "Degraderet" (Ollama utilgængelig, DB og storage ok), som forventet uden en kørende Ollama.
- Sletteknappen blev **ikke** testet i browseren (udløser `window.confirm`, som ville blokere automatiseringen) — DELETE-endpointet er allerede dækket af `test_api.py` på backend-siden.
- `ruff check`/`ruff format --check`/`pytest --cov` på backend stadig grønne efter CORS-tilføjelsen (135 tests, 93 % samlet dækning — uændret fra fase 4, da ændringen kun er wiring).

**Review (udfyldes af den studerende):**

## 2026-10-19 – Fase 4: Azure/lokal backup

**Genereret:**
- `backend/app/config.py`: `backup_backend: Literal["local","azure"]` med case-insensitiv normalisering (`field_validator(mode="before")`) og en `model_validator(mode="after")`, der **fejler ved Settings-konstruktion** (dvs. så tidligt som overhovedet muligt — allerede når `app.db` importeres, da `db.py` kalder `get_settings()` ved modul-load), hvis `BACKUP_BACKEND=azure` er sat uden `AZURE_STORAGE_CONNECTION_STRING` eller `AZURE_STORAGE_ACCOUNT_URL`. Ingen stille fallback til lokal lagring.
- `backend/app/storage/`: `base.py` (`BackupInfo`, `BackupStorage`-protokol), `local.py` (`LocalStorage` — rigtig filsystem-I/O, brugt i alle tests via `tmp_path`), `azure_blob.py` (`AzureBlobStorage`, auth via connection string eller `DefaultAzureCredential`, opretter containeren hvis den mangler, normaliserer "blob findes ikke" til `FileNotFoundError` så services-laget ikke skal kende til Azure-specifikke exceptions), `__init__.py` (`get_backup_storage(settings)` — det **eneste** sted der læser `backup_backend`, plus en cached FastAPI-dependency).
- `backend/app/services/backup.py`: `export_snapshot` (bygger snapshot-JSON'en fra §7.1 via den eksisterende `ComponentRead`-serialisering — genbruger valideringslogikken i stedet for at duplikere den), `create_backup`, `list_backups` (beriger storage-lagets rå liste med `component_count` ved at downloade og parse hver snapshot — se Antagelser), `restore_backup` (schema_version → component_count-sanity-check → sha256 → validér hver komponent med Pydantic **før** databasen overhovedet røres → slet og genindsæt i én transaktion med rollback ved uventet DB-fejl).
- `backend/app/routers/backup.py`: `POST/GET /api/backup`, `POST /api/backup/restore` (manuelt `confirm`-tjek → 400, ikke Pydantic-422, så det matcher SPEC §9.1's testkrav ordret).
- `GET /api/health` viser nu også `storage`-status (kalder `storage.list()`), `backup_backend` og `backup_destination` (container-navn eller mappe — aldrig connection string).
- `.env.example`, `docker-compose.yml` (backend får nu `BACKUP_BACKEND`/`LOCAL_BACKUP_DIR`/`AZURE_*`-env samt et `./backups:/app/backups`-volume), `README.md` (ny sektion om at skifte backend).

**Antagelser:**
- **`list_backups()` downloader og parser hver backup-fil for at finde `component_count`**, i stedet for at kræve det af `BackupStorage.list()` selv — det ville have krævet enten en Azure-specifik `metadata`-parameter i `upload()` (et brud på den spec'ede Protocol-signatur) eller at indkode antallet i filnavnet (i konflikt med det eksakte, spec'ede filnavnsformat `inventory-<UTC-tidsstempel>.json`). For et personligt projekt med et håndfuldt backups er downloadet pr. liste-kald acceptabelt; værd at genbesøge, hvis antallet af backups bliver stort.
- **`BackupInfo.component_count` er `None`, indtil service-laget udfylder det** — storage-laget kan ikke vide det billigt (Azure blob-metadata uden download, lokal fil uden parsing), så typen er bevidst optional i stedet for at tvinge et gæt.
- **Restore validerer *alle* komponenter, før databasen røres overhovedet** — "rollback ved fejl" dækker derfor primært uventede DB-fejl under selve slet-og-genindsæt-transaktionen (testet med en simuleret `commit()`-fejl), ikke en ugyldig komponent (den opdages tidligere og rammer aldrig databasen).
- **`restore_backup` tjekker desuden at `component_count` matcher det faktiske antal komponenter** i filen — ikke et eksplicit SPEC-krav, men en gratis, billig sanity-check mod korrupte filer, konsistent med projektets fokus på kvalitetssikring.
- **`AzureBlobStorage`'s `download()` normaliserer Azures `ResourceNotFoundError` til `FileNotFoundError`**, så `services/backup.py` kan håndtere "backup findes ikke" ens for begge backends uden at importere Azure-specifikke exceptions.
- **`APP_VERSION` i snapshot-formatet er en hardcodet konstant** (`"0.1.0"`, matcher `pyproject.toml`) — ikke læst dynamisk fra pakke-metadata, da det ville kræve en ekstra afhængighed for et énlinjes-formål.

**Kendte risici / svagheder:**
- **Azure-stien er udelukkende testet med mocket `BlobServiceClient`** (ingen Azure-konto endnu, jf. tidligere faser). Når du opretter en konto, bør du som minimum køre en rigtig backup → list → restore-cyklus og bekræfte at `GET /api/health`/`GET /api/backup` viser `"azure"` og containernavnet uden at lække connection-stringen (testet her kun med en mocket storage-dependency, ikke en reelt kørende Azure-forbindelse gennem hele stacken).
- **`docker compose up` er stadig ikke kørt i denne session** — `./backups:/app/backups`-volumet og `BACKUP_BACKEND`-env-gennemstrømningen er kun valideret ved at parse `docker-compose.yml` som YAML, ikke ved faktisk opstart.
- **Ingen auto-backup** (§7.3's valgfrie "backup efter N ændringer eller via cron-endpoint") er implementeret — vurderet som ægte valgfrit ("valgfri" i spec'en) og udeladt for at holde fasen fokuseret; `POST /api/backup` kan allerede kaldes manuelt fra en cron-job på serveren, hvis det bliver relevant.
- **`routers/backup.py` linje 16 og 52-53 samt `main.py`'s fejl-grene er ikke dækket** — mindre, symmetriske fejlhåndteringsgrene identisk i mønster med allerede testede grene andre steder.

**Tests der dækker det:**
- `test_config.py` (6 tests): default `local`, case-insensitiv normalisering, ugyldig værdi afvist, `azure` uden credentials fejler (regex-matcher den eksakte fejlbesked), `azure` med hhv. connection string og account URL accepteret.
- `test_storage.py` (7 tests — stod fejlagtigt som 8): factory returnerer `LocalStorage`/`AzureBlobStorage` korrekt (Azure-klient mocket for både connection-string- og account-url-stien), container-oprettelse tolererer `ResourceExistsError`, `LocalStorage`-roundtrip, manglende fil → `FileNotFoundError`, irrelevante filer ignoreres af `list()`.
- `test_backup.py` (15 tests — stod fejlagtigt som 19): fuld roundtrip (backup → simuleret datatab → restore → identisk lager), tamperet hash afvist, ukendt `schema_version` afvist, `component_count`-mismatch afvist, ugyldig JSON afvist, ugyldig komponent afvist uden at ændre databasen, ukendt backup-navn → `FileNotFoundError`/404, uventet DB-fejl under restore → rollback (verificeret at originaldata stadig er der), `list_backups` håndterer en ulæselig backup-fil uden at crashe, og den fulde API-cyklus (opret → backup → ny komponent → restore → kun de oprindelige komponenter findes).
- `test_api.py`: `/api/health` lækker aldrig `AZURE_STORAGE_CONNECTION_STRING`, selv når Azure er den aktive backend.
- `ruff check`/`ruff format --check` grønne. `pytest --cov`: 93 % samlet; 100 % på `services/backup.py` (§9.1 kræver ≥80 % her), `storage/base.py` og `storage/local.py`.

**Review (udfyldes af den studerende):**

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
- `test_llm_parsing.py` (7 tests dengang, nu 8 — code review-posten ovenfor tilføjede en `LLMUnavailableError`-test): gyldigt svar, ugyldig JSON → retry, to fejl → fallback, opfundet `build_id` afvist af `validate`-callback → fallback, gyldigt `build_id` accepteret, og to injection-tests der konkret beviser at en indlejret `</data>` bliver escaped i stedet for at bryde ud af data-blokken.
- `test_pipeline.py` (12 tests — rettet, stod fejlagtigt som 14): den krævede "headless lokal-AI"-scenarie end-to-end med fake LLM, inkompatibelt lager → ingen builds og intet rangerings-kald, LLM-fejl på begge trin → deterministisk fallback, hårde minimumskrav (VRAM/RAM/lager/kerner) i `prefilter_candidates`, manglende GPU-match → korrekt `missing`, og den deterministiske scorers præferencer (lav effekt, lille formfaktor).
- `test_api_llm_endpoints.py` (9 tests dengang, nu 12 — code review-posten ovenfor tilføjede en 503- og en 422-test samt CORS-på-500-testen): `/search` (kandidater, 404 ved tomt resultat, 400 når slået fra), `/extract` (web-lookup, direkte LLM-viden når slået fra, 400 uden valgt candidate, 422 ved varigt ugyldigt LLM-svar), `/recommend` (et build, tom-lager → `missing`).
- `ruff check`/`ruff format --check` grønne. `pytest --cov`: 93 % samlet; 100 % på `llm/parsing.py` og `llm/prompts.py`, 99 % på `pipeline/recommend.py` (§9.1 kræver ≥80 % her — opfyldt).

**Review (udfyldes af den studerende):**

## 2026-10-19 – Fase 2: Kompatibilitet

**Genereret:**
- `backend/app/compatibility/types.py`: `CandidateComponent`, `Build`, `RuleResult`, `BuildEvaluation` (med `warnings`-property for `unknown`-resultater), `EngineResult`. Ny fil ift. SPEC.md's mappestruktur (som kun nævner `rules.py` + `engine.py`) — delte typer samlet ét sted for at undgå cirkulære imports og duplikering mellem de to.
- `backend/app/compatibility/rules.py`: alle 15 regler fra SPEC §6 (tabellen har 15 rækker, inkl. `display_output_available`), hver som en ren funktion `(Build) -> RuleResult`. `psu_wattage_sufficient` bruger de nye konfigurerbare `PSU_BASE_WATT_W`/`PSU_SAFETY_MARGIN`-settings (tilføjet til `config.py` og `.env.example`).
- `backend/app/compatibility/engine.py`: `generate_builds()` kombinerer kandidater pr. kategori (begrænset af `top_n`, default 5) og beholder kun builds hvor ingen regel fejler. `missing` rapporterer kategorier uden nogen kandidater overhovedet.
- `backend/tests/fixtures/sample_inventory.py`: en minimal, håndlavet, fuldt kompatibel baseline (separat fra `app/seed.py`, som er stort og realistisk til demo, ikke minimalt til assertions) + en `with_specs()`-hjælpefunktion til at lave varianter.
- `backend/tests/test_rules.py` (56 tests — stod fejlagtigt som 41 her, en simpel optællingsfejl ved skrivningen, rettet efter en senere nøjagtighedsgennemgang af denne log) og `backend/tests/test_engine.py` (8 tests).

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
