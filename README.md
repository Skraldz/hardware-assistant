# Hardware Assistant

AI-drevet hardwareassistent og lagersystem. Se `SPEC.md` for den fulde tekniske spec og `CLAUDE.md` for projektrammerne. Eksamenskrav er opsummeret i `docs/exam-requirements.md`.

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
