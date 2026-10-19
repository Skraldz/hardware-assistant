# SPEC — Hardware Assistant (AI-drevet hardwarelager og pc-sammensætter)

> Eksamensprojekt i valgfaget **Programmering og AI**, Zealand (3. semester).
> Denne spec er skrevet til Claude Code. Læs hele dokumentet før du skriver kode, og arbejd fase for fase (se §11).

---

## 1. Formål

En Python-applikation, hvor brugeren registrerer sine egne hardwarekomponenter i en database og derefter beskriver et projekt i fri tekst (fx *"Jeg skal bruge en headless pc til lokal AI – hvilke af mine dele skal jeg bruge?"*). En lokal sprogmodel (Ollama) fortolker behovet, og systemet foreslår en **kompatibel** konfiguration udelukkende ud fra brugerens beholdning. Inventaret kan sikkerhedskopieres til og gendannes fra **Azure Blob Storage**.

### 1.1 Eksamenskontekst – hvad der vægtes (vigtigt for prioriteringen)
Bedømmelsen sker efter disse læringsmål, så de styrer hvad der er vigtigst:
1. **Kvalitetssikring af AI-output** – modellen må aldrig være eneste sandhed om kompatibilitet.
2. **Unit tests** – grundig, meningsfuld testdækning med pytest.
3. **Vurdering af AI-genereret kode** – udviklingen dokumenteres i `docs/ai-log.md` (se §10).
4. **Cloud-upload af data** – formkrav (Azure, se §7).
5. Funktionel Python-applikation.

Frontenden er sekundær. Hold den simpel.

---

## 2. Kerneprincip: "LLM'en foreslår, reglerne verificerer"

- Sprogmodellen bruges **kun** til:
  - at oversætte fri tekst til strukturerede krav (`ProjectRequirements`),
  - at udtrække specs fra et hardwarenavn ved indtastning (som brugeren bekræfter),
  - at rangere og begrunde blandt builds, der **allerede er verificeret kompatible**.
- Al kompatibilitet afgøres af **deterministisk Python-kode** (`compatibility/`), som er fuldt unit-testet.
- Al LLM-output valideres med **Pydantic v2**-skemaer. Ugyldigt output → én retry med valideringsfejlen som feedback → derefter deterministisk fallback. Systemet må aldrig crashe eller returnere et ikke-verificeret build pga. dårligt AI-svar.
- **Ingen agentisk tool-calling.** Orkestreringen er en fast pipeline i backend-koden.

---

## 3. Arkitektur

Docker Compose med følgende services:

| Service | Teknologi | Rolle |
|---|---|---|
| `db` | MariaDB 11 | Hardwareinventar |
| `ollama` | Ollama | Lokal LLM (model konfigurerbar via env, default `qwen2.5:7b-instruct`) |
| `backend` | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, httpx | API, pipeline, kompatibilitetsmotor, Azure-backup |
| `frontend` | React + Vite (minimal) | Inventar-CRUD, projekt-forespørgsel, backup-knapper |
| `searxng` | SearXNG | **Valgfri / fase 5.** Spec-berigelse fra nettet. Slås til med `ENABLE_WEB_LOOKUP=true` |

GPU-passthrough til Ollama skal være valgfri (kommenteret blok i compose-filen).

### 3.1 Mappestruktur
```
hardware-assistant/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                # FastAPI app + routers
│   │   ├── config.py              # pydantic-settings, læser env
│   │   ├── db.py                  # engine, session
│   │   ├── models.py              # SQLAlchemy ORM
│   │   ├── schemas/
│   │   │   ├── components.py      # Pydantic: specs pr. kategori
│   │   │   ├── requirements.py    # ProjectRequirements (LLM-output)
│   │   │   └── builds.py          # BuildProposal, BuildResult
│   │   ├── llm/
│   │   │   ├── client.py          # OllamaClient (httpx), structured output
│   │   │   ├── prompts.py         # alle prompts samlet ét sted
│   │   │   └── parsing.py         # validering + retry-logik
│   │   ├── compatibility/
│   │   │   ├── rules.py           # én funktion pr. regel
│   │   │   └── engine.py          # kombinerer regler, genererer gyldige builds
│   │   ├── pipeline/
│   │   │   └── recommend.py       # orkestrering trin 1–5 (§5)
│   │   ├── storage/
│   │   │   ├── base.py            # BackupStorage-protokol
│   │   │   ├── azure_blob.py
│   │   │   └── local.py           # fallback + bruges i tests
│   │   ├── services/
│   │   │   ├── inventory.py
│   │   │   └── backup.py          # export/import af snapshot
│   │   └── routers/
│   │       ├── components.py
│   │       ├── recommend.py
│   │       └── backup.py
│   └── tests/
│       ├── conftest.py            # SQLite in-memory, fake LLM, local storage
│       ├── fixtures/              # eksempel-inventar, LLM-svar (gyldige + ugyldige)
│       ├── test_rules.py
│       ├── test_engine.py
│       ├── test_llm_parsing.py
│       ├── test_pipeline.py
│       ├── test_backup.py
│       └── test_api.py
├── frontend/
├── infra/                         # valgfri: Terraform til Azure Storage Account
└── docs/
    ├── ai-log.md
    └── architecture.md
```

---

## 4. Datamodel (hybrid)

### 4.1 Tabel `components`
| Kolonne | Type | Note |
|---|---|---|
| `id` | int PK | |
| `category` | enum | `cpu, motherboard, ram, gpu, storage, psu, case, cooler` |
| `name` | varchar(200) | Brugerens navn, fx "RTX 3060 12GB" |
| `manufacturer` | varchar(100) nullable | |
| `quantity` | int ≥ 0 | |
| `condition` | enum | `new, used, faulty` – `faulty` udelukkes altid fra builds |
| `specs` | JSON | Kategorispecifikke felter, valideres af Pydantic (§4.2) |
| `specs_source` | enum | `manual, llm_extracted, web_lookup` |
| `specs_verified` | bool | `true` når brugeren har bekræftet |
| `notes` | text nullable | |
| `created_at`, `updated_at` | datetime | |

Brug SQLAlchemys generiske `JSON`-type, så samme model kører på MariaDB og SQLite (tests).

### 4.2 Specs pr. kategori (Pydantic, `schemas/components.py`)
Brug en discriminated union på `category`. Minimumsfelter:

- **cpu**: `socket`, `cores`, `threads`, `tdp_w`, `integrated_graphics: bool`, `memory_type: list[DDR4|DDR5]`
- **motherboard**: `socket`, `form_factor (ATX|mATX|ITX|EATX)`, `memory_type`, `memory_slots`, `max_memory_gb`, `m2_slots`, `sata_ports`, `pcie_x16_slots`
- **ram**: `memory_type`, `capacity_gb_per_module`, `modules`, `speed_mts`, `form (DIMM|SODIMM)`
- **gpu**: `vram_gb`, `tdp_w`, `length_mm`, `pcie_power_connectors: list[str]`, `vendor (nvidia|amd|intel)`
- **storage**: `interface (nvme|sata_ssd|sata_hdd)`, `capacity_gb`, `form_factor (m2_2280|2_5|3_5)`
- **psu**: `wattage_w`, `form_factor (ATX|SFX)`, `pcie_power_connectors: list[str]`, `efficiency_rating` (valgfri)
- **case**: `supported_form_factors: list`, `max_gpu_length_mm`, `max_cooler_height_mm`, `psu_form_factor`, `drive_bays_3_5`, `drive_bays_2_5`
- **cooler**: `type (air|aio)`, `supported_sockets: list`, `height_mm` (air), `radiator_mm` (aio), `tdp_rating_w`

Ukendte felter er tilladt som `None`. Regler, der mangler data, skal returnere **`unknown`** (ikke pass/fail), og builds med `unknown` markeres med en advarsel.

---

## 5. Anbefalingspipeline (`pipeline/recommend.py`)

Input: `{ "prompt": "fri tekst", "max_builds": 3 }`

1. **Fortolk behov (LLM)** → `ProjectRequirements`:
   ```
   use_case: str
   headless: bool
   required_categories: list[Category]
   min_vram_gb: int | None
   min_ram_gb: int | None
   min_storage_gb: int | None
   min_cpu_cores: int | None
   prefer_low_power: bool
   prefer_small_form_factor: bool
   notes: str
   ```
   Brug Ollamas structured output (`format` = JSON-schema fra Pydantic-modellen). Valider → retry én gang med fejlbesked → fallback til konservative defaults + advarsel i svaret.
2. **Forfiltrering (deterministisk)**: hent komponenter med `quantity > 0` og `condition != faulty`; frasortér dem, der ikke opfylder hårde minimumskrav.
3. **Generér gyldige builds (deterministisk)**: kompatibilitetsmotoren kombinerer kandidater og beholder kun builds, hvor alle regler er `pass` eller `unknown`. Begræns kombinatorikken (fx top-N pr. kategori efter relevans), så den kører hurtigt med ~200 komponenter.
   - `headless: true` → GPU er valgfri, medmindre `min_vram_gb` er sat.
   - Ingen GPU og CPU uden integreret grafik → kun tilladt hvis `headless`.
4. **Rangér og begrund (LLM)**: send de verificerede builds (som ID'er + nøglespecs) til modellen. Den returnerer `ranking: list[{build_id, reason}]`. **Valider at alle `build_id` findes i kandidatlisten**. Opfundne ID'er afvises. Fallback: deterministisk score.
5. **Endelig verifikation**: kør kompatibilitetsmotoren igen på det valgte build (forsvar i dybden) og returnér:
   ```
   builds: [{ components, rule_results, warnings, reason, score }]
   missing: list[Category]   # kategorier brugeren mangler for projektet
   llm_used: { interpret: ok|retried|fallback, rank: ok|retried|fallback }
   ```

Hvis ingen gyldige builds kan laves: returnér `missing` med en forklaring af hvad der mangler (fx "Ingen PSU med nok watt til RTX 3090 + i9").

---

## 6. Kompatibilitetsregler (`compatibility/rules.py`)

Hver regel er en ren funktion: `def rule(build: Build) -> RuleResult` med `status: pass|fail|unknown` og `message`. Minimum:

| Regel | Logik |
|---|---|
| `cpu_socket_matches_board` | `cpu.socket == motherboard.socket` |
| `ram_type_matches` | RAM-type ∈ board.memory_type og ∈ cpu.memory_type |
| `ram_form_is_dimm` | desktop-board kræver DIMM |
| `ram_slots_sufficient` | `ram.modules ≤ board.memory_slots` |
| `ram_capacity_within_board_max` | |
| `board_fits_case` | `board.form_factor ∈ case.supported_form_factors` |
| `gpu_fits_case` | `gpu.length_mm ≤ case.max_gpu_length_mm` |
| `cooler_fits_case` | luftkøler: `height_mm ≤ case.max_cooler_height_mm` |
| `cooler_supports_socket` | |
| `cooler_handles_tdp` | `cooler.tdp_rating_w ≥ cpu.tdp_w` |
| `psu_wattage_sufficient` | `psu.wattage_w ≥ (cpu.tdp_w + gpu.tdp_w + 75 W base) × 1.3` (konstanter i config) |
| `psu_has_gpu_connectors` | GPU'ens strømstik ⊆ PSU'ens |
| `psu_fits_case` | |
| `storage_slots_available` | NVMe-drev ≤ m2_slots, SATA-drev ≤ sata_ports |
| `display_output_available` | GPU findes eller CPU har iGPU – springes over hvis headless |

Sikkerhedsmargin og base-watt skal være konfigurerbare og dokumenteret.

---

## 7. Azure backup/sync (`storage/`, `services/backup.py`)

### 7.1 Snapshot-format
```json
{
  "schema_version": 1,
  "created_at": "2026-10-19T12:00:00Z",
  "app_version": "0.1.0",
  "component_count": 42,
  "sha256": "<hash af components-array>",
  "components": [ ... ]
}
```
Filnavn: `inventory-<UTC-tidsstempel>.json`.

### 7.2 Storage-abstraktion
```python
class BackupStorage(Protocol):
    def upload(self, name: str, data: bytes) -> str: ...
    def list(self) -> list[BackupInfo]: ...
    def download(self, name: str) -> bytes: ...
```
- `AzureBlobStorage` – `azure-storage-blob`. Auth via `AZURE_STORAGE_CONNECTION_STRING` **eller** `DefaultAzureCredential` + `AZURE_STORAGE_ACCOUNT_URL`. Container: `AZURE_BACKUP_CONTAINER` (default `inventory-backups`), oprettes hvis den mangler.
- `LocalStorage` – skriver til `LOCAL_BACKUP_DIR` (default `/app/backups`, mountet som Docker-volume `./backups:/app/backups`, så filerne overlever en genstart af containeren). Bruges i alle tests.

### 7.2.1 Valg af backend via `.env` (krav)
Brugeren vælger backup-destination **udelukkende** i `.env`. Der må ikke være kodeændringer for at skifte:

```dotenv
# --- Backup ---
# Vælg hvor inventar-backups gemmes: local | azure
BACKUP_BACKEND=local

# Bruges når BACKUP_BACKEND=local
LOCAL_BACKUP_DIR=/app/backups

# Bruges når BACKUP_BACKEND=azure (angiv ENTEN connection string ELLER account URL)
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_ACCOUNT_URL=
AZURE_BACKUP_CONTAINER=inventory-backups
```

Krav til implementeringen:
- `config.py` definerer `backup_backend: Literal["local", "azure"] = "local"` med pydantic-settings. Værdien er case-insensitive (`AZURE` = `azure`). Ugyldige værdier giver en tydelig fejl ved opstart.
- En factory `get_backup_storage(settings) -> BackupStorage` i `storage/__init__.py` vælger implementeringen. Det er det **eneste** sted i koden, der kigger på `BACKUP_BACKEND`. Routers og services kender kun `BackupStorage`-protokollen (dependency injection via FastAPI `Depends`).
- **Fail fast**: Er `BACKUP_BACKEND=azure` sat uden connection string eller account URL, skal backend fejle ved opstart med en klar besked (fx *"BACKUP_BACKEND=azure kræver AZURE_STORAGE_CONNECTION_STRING eller AZURE_STORAGE_ACCOUNT_URL"*). Der må **ikke** stille og roligt faldes tilbage til lokal backup, for så tror brugeren, at data ligger i skyen.
- `GET /api/health` og `GET /api/backup` viser aktiv backend (`"backup_backend": "azure"`) og destination (container-navn eller mappe, **aldrig** secrets).
- Frontenden viser aktiv backend ved backup-knapperne, fx "Backup → Azure (inventory-backups)".
- `.env.example` indeholder blokken ovenfor med kommentarer. README forklarer, hvordan man skifter.
- Tests (`test_backup.py` / `test_config.py`): factory returnerer `LocalStorage` for `local`, `AzureBlobStorage` for `azure` (Azure-klienten mockes), store/små bogstaver accepteres, ugyldig værdi giver fejl, `azure` uden credentials giver fejl, og health-endpoint lækker ikke connection string.

### 7.3 Funktionalitet
- **Backup**: eksportér hele inventaret → upload.
- **List**: vis tilgængelige backups (navn, tidspunkt, antal, størrelse).
- **Restore**: download → verificér `sha256` og `schema_version` → valider hver komponent med Pydantic → erstat inventaret i **én transaktion** (rollback ved fejl). Kræver `confirm: true` i requesten.
- **Auto-backup** (valgfri): backup efter N ændringer eller via et endpoint, man kan kalde fra cron.

### 7.4 Infra (valgfri, `infra/`)
Lille Terraform-konfiguration: resource group, storage account (privat, TLS 1.2, ingen public blob access), container. Output: account URL.

---

## 8. API (FastAPI)

| Metode | Path | Beskrivelse |
|---|---|---|
| GET | `/api/components` | Liste, filtrér på `category` |
| POST | `/api/components` | Opret (specs valideres) |
| GET/PUT/DELETE | `/api/components/{id}` | |
| POST | `/api/components/extract` | `{ "name": "RTX 3060 12GB" }` → LLM-forslag til kategori + specs. **Gemmes ikke**: brugeren bekræfter og sender via POST |
| POST | `/api/recommend` | Pipeline (§5) |
| POST | `/api/backup` | Lav backup |
| GET | `/api/backup` | List backups |
| POST | `/api/backup/restore` | `{ "name": "...", "confirm": true }` |
| GET | `/api/health` | DB, Ollama og storage-status |

OpenAPI-docs skal være tilgængelige på `/docs`.

---

## 9. Kvalitet, test og sikkerhed

### 9.1 Tests (pytest)
- **Ingen test må kræve Ollama, MariaDB eller Azure.** Brug:
  - SQLite in-memory via SQLAlchemy,
  - en `FakeLLMClient` der returnerer svar fra `tests/fixtures/` (gyldige, ugyldig JSON, forkert skema, opfundne build-ID'er, tomme svar),
  - `LocalStorage` med `tmp_path`.
- Krævede testområder:
  - **Hver regel** i §6: pass, fail og unknown (manglende data).
  - **Engine**: kendt inventar → forventede gyldige builds; inkompatibelt inventar → ingen builds + korrekt `missing`.
  - **LLM-parsing**: gyldigt svar, ugyldig JSON → retry, to fejl → fallback, hallucineret build-ID → afvist.
  - **Pipeline end-to-end** med fake LLM, inkl. scenariet *"headless lokal-AI"*.
  - **Backup**: roundtrip (export → upload → download → restore giver identisk inventar), forkert hash → afvist, ugyldig komponent → hele restore rulles tilbage, `confirm` mangler → 400.
  - **API**: statuskoder og validering med FastAPI `TestClient`.
- Mål: ≥ 80 % coverage på `compatibility/`, `llm/parsing.py`, `pipeline/` og `services/backup.py` (`pytest-cov`).
- Én valgfri integrationstest mod rigtig Ollama, markeret `@pytest.mark.integration` og skippet som standard.

### 9.2 Kodestandard
- Type hints overalt, `ruff` (lint + format), ingen ubrugte imports.
- Alle prompts i `llm/prompts.py`, aldrig inline.
- Konfiguration via `pydantic-settings`, ingen hardcodede værdier.
- Logging med `logging`, inkl. når LLM-retry eller fallback bruges.

### 9.3 Sikkerhed og ansvarlig AI
- Ingen secrets i repo. `.env.example` med placeholders, `.env` i `.gitignore`.
- Kun ORM/parametriserede queries.
- Brugerinput (komponentnavne, noter) sendes til LLM'en: afgræns det tydeligt i prompten som data, og stol aldrig på instruktioner i det (prompt injection). Lav en test med et komponentnavn, der indeholder en injection-tekst.
- Al AI-inferens kører lokalt. Kun inventar-snapshots sendes til Azure. Det skal stå i `docs/architecture.md`.
- Specs fra LLM eller web markeres `specs_verified=false`, indtil brugeren bekræfter dem.

---

## 10. AI-udviklingslog (`docs/ai-log.md`) – vigtigt for eksamen

Den studerende skal kunne vise, hvordan AI-genereret kode er blevet vurderet og forbedret. Derfor:

- Efter hver fase/feature tilføjer Claude Code en post:
  ```
  ## <dato> – <feature>
  **Genereret:** hvilke filer/funktioner
  **Antagelser:** hvad der er antaget uden at være specificeret
  **Kendte risici / svagheder:** hvad en reviewer bør kigge efter
  **Tests der dækker det:** ...
  **Review (udfyldes af den studerende):** fund, rettelser, begrundelse
  ```
- Vær ærlig om usikkerheder, så de kan bruges i reviewet. Fejl skal ikke skjules.
- Små, fokuserede commits pr. feature, så diffs kan vises til eksamen.

---

## 11. Faser og acceptkriterier

| Fase | Indhold | Færdig når |
|---|---|---|
| **1. Fundament** | Compose (db, backend), modeller, Pydantic-schemas, CRUD-API, testopsætning | `docker compose up` virker, CRUD-tests grønne |
| **2. Kompatibilitet** | Alle regler + engine, uden LLM | Regel- og engine-tests grønne, coverage ≥ 80 % |
| **3. LLM-integration** | OllamaClient, prompts, parsing/retry/fallback, `/extract`, pipeline | Pipeline-tests med fake LLM grønne; manuel test mod Ollama giver et fornuftigt "headless lokal-AI"-build |
| **4. Azure backup** | Storage-abstraktion, Azure + local, backup/list/restore, (Terraform) | Backup-tests grønne; manuel backup ses i Azure-containeren |
| **5. Frontend + polish** | Minimal React-UI, health-endpoint, `docs/architecture.md`, valgfri SearXNG | Hele flowet kan demonstreres på 5 min |

Lav seed-data (`backend/app/seed.py`) med ~25 realistiske komponenter, der indeholder mindst én bevidst inkompatibilitet (fx en AM4-CPU og et LGA1700-board), til demo og tests.

---

## 12. Uden for scope
- Prissammenligning, købslinks, webshop-integration
- Bærbare, servere i rack-format og custom vandkøling
- Brugerlogin/multi-user
- Agentisk tool-calling og autonome AI-handlinger
