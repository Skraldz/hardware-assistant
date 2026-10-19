# Hardware Assistant

AI-drevet hardwareassistent og lagersystem. Se `SPEC.md` for den fulde tekniske spec og `CLAUDE.md` for projektrammerne. Eksamenskrav er opsummeret i `docs/exam-requirements.md`.

## Funktioner

- **Hardwarelager**: registrér egne pc-komponenter (CPU, bundkort, RAM, GPU, lager, strømforsyning, kabinet, køler) med kategorispecifikke specifikationer.
- **Automatisk specifikationsopslag**: skriv et komponentnavn (fx "RTX 2060 SUPER"), lad systemet søge på nettet og udtrække specs med en lokal AI-model — du bekræfter resultatet, før det gemmes.
- **AI-drevet build-anbefaling**: beskriv et projekt i fri tekst (fx "headless pc til lokal AI"), og få foreslået kompatible builds sammensat udelukkende af din egen beholdning.
- **Deterministisk kompatibilitetstjek**: hver foreslået build verificeres af regelbaseret kode (socket, RAM-type, strømforbrug, fysisk pladsforhold osv.) — AI'en foreslår aldrig noget, reglerne ikke har godkendt.
- **Backup/gendannelse**: sikkerhedskopiér hele lageret til disk eller Azure Blob Storage, og gendan det igen med integritetstjek (sha256, schema-version).
- **Minimal web-UI**: React-frontend til lager, anbefalinger og backup, med lys/mørk visning og dansk/engelsk sprogvalg (begge huskes i browseren).

## Sådan virker systemet

Kerneprincippet er **"LLM'en foreslår, reglerne verificerer"** (se `SPEC.md` §2 og `docs/architecture.md` for et services-diagram og den fulde gennemgang):

1. En lokal sprogmodel (Ollama) fortolker brugerens fri tekst til strukturerede krav.
2. Deterministisk Python-kode (`backend/app/compatibility/`) kombinerer kandidater fra lageret og beholder kun de builds, hvor alle kompatibilitetsregler er opfyldt.
3. Sprogmodellen rangerer og begrunder blandt de allerede verificerede builds — den kan aldrig foreslå noget, koden ikke har godkendt.
4. Alt struktureret AI-output valideres med Pydantic; ugyldigt output giver én retry, derefter en sikker fallback. Systemet crasher aldrig og returnerer aldrig et ikke-verificeret build på grund af et dårligt AI-svar.

Al AI-inferens kører lokalt (Ollama på din egen server) — kun inventar-snapshots forlader maskinen, og kun hvis du selv vælger Azure som backup-destination.

## Krav

- **Docker** og **Docker Compose** — til at køre hele stakken (database, backend, lokal LLM, websøgning, frontend) med ét kommando.
- Nok hukommelse/diskplads til at køre en lokal sprogmodel i Ollama (default `qwen2.5:7b-instruct`). En GPU anbefales for rimelig svartid, men er ikke påkrævet — se GPU-passthrough-blokken i `docker-compose.yml`.
- Til lokal udvikling uden Docker: **Python 3.12+** (backend) og **Node.js 20+** (frontend).
- Ingen Azure-konto er påkrævet som standard — backup bruger lokal diskplads, medmindre `BACKUP_BACKEND=azure` vælges eksplicit i `.env`.

## Kør projektet

```bash
cp .env.example .env   # udfyld adgangskoder
docker compose up -d --build
```

Backend starter på `http://localhost:8000` (se `/docs` for OpenAPI). Frontend starter på `http://localhost:4173`. Databasen oprettes og seedes automatisk ved første opstart (tom database).

Åbner du frontenden fra en anden maskine end serveren (fx `http://192.168.1.50:4173`), finder den selv backenden på samme hostname, port `APP_PORT` — ingen konfiguration nødvendig.

## Backup: local eller Azure

Inventaret kan sikkerhedskopieres til disk eller til Azure Blob Storage. Skiftes **udelukkende** via `.env` — ingen kodeændringer:

```dotenv
BACKUP_BACKEND=local   # eller: azure
```

- **`local`** (default): skriver til `LOCAL_BACKUP_DIR` (default `/app/backups`), som er mountet som `./backups` på serveren, så filerne overlever en genstart.
- **`azure`**: kræver `AZURE_STORAGE_CONNECTION_STRING` **eller** `AZURE_STORAGE_ACCOUNT_URL` (med `DefaultAzureCredential`) udfyldt i `.env`. Containeren (`AZURE_BACKUP_CONTAINER`, default `inventory-backups`) oprettes automatisk, hvis den ikke findes. Mangler begge, **fejler backend ved opstart** — den falder aldrig stille tilbage til lokal lagring.

Aktiv backend og destination (aldrig secrets) vises i `GET /api/health` og `GET /api/backup`.

Backup-endpoints: `POST /api/backup` (lav backup), `GET /api/backup` (list backups), `POST /api/backup/restore` (`{"name": "...", "confirm": true}` — erstatter hele inventaret i én transaktion).

## Udvikling og tests (uden Docker)

Tests kører mod SQLite in-memory og kræver ikke MariaDB, Ollama eller Azure.

```bash
cd backend
pip install -e ".[dev]"
ruff check .
ruff format .
pytest --cov
```

## Frontend-udvikling (uden Docker)

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, forventer backend på :8000
```

## Status

Se `docs/ai-log.md` for en logget gennemgang af hver fase (hvad er genereret, antagelser, kendte risici, testdækning).
