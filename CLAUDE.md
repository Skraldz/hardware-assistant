# CLAUDE.md — Hardware Assistant

Denne fil læses automatisk af Claude Code. Den fulde tekniske spec ligger i **SPEC.md**, og den skal læses før du skriver kode.

## Projektet kort
Eksamensprojekt i valgfaget **Programmering og AI** (Zealand, IT-Teknolog, 3. semester, underviser Zuhair Haroon Khan). Applikationen er en AI-drevet hardwareassistent og et lagersystem:
- Brugeren registrerer sine egne pc-komponenter i en database (MariaDB).
- Brugeren beskriver et projekt i fri tekst, fx *"headless pc til lokal AI"*.
- En lokal LLM (Ollama) fortolker behovet, deterministisk Python-kode verificerer kompatibiliteten, og LLM'en rangerer og begrunder de gyldige builds.
- Inventaret kan sikkerhedskopieres lokalt eller til Azure Blob Storage. Det vælges i `.env` (`BACKUP_BACKEND=local|azure`).

Stack: Docker Compose, Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Ollama, MariaDB og en minimal React-frontend. SearXNG er valgfri.

## Problemformulering
**Hovedspørgsmål:** Hvordan kan der udvikles en Python-applikation, som med en lokal sprogmodel kan sammensætte en kompatibel pc-konfiguration ud fra brugerens egen hardwarebeholdning og en projektbeskrivelse i fri tekst? Og hvordan kan AI-værktøjer bruges i udviklingen, samtidig med at kvaliteten af både den genererede kode og modellens forslag sikres?

**Underspørgsmål:**
1. Hvordan modelleres beholdningen i en database, så komponenternes egenskaber kan bruges til automatisk kompatibilitetstjek?
2. Hvordan oversætter en lokal LLM fri tekst til strukturerede krav, og hvordan valideres output (Pydantic og regelbaseret verifikation), så hallucinerede eller inkompatible forslag bliver afvist?
3. Hvordan er AI brugt som programmeringsassistent, hvilke fejl blev fundet i AI-genereret kode, og hvordan blev de rettet?
4. Hvordan sikrer unit tests kompatibilitetsregler, datavalidering og håndtering af ugyldigt AI-output?
5. Hvordan uploades data til cloud (Azure), og hvilke overvejelser om datasikkerhed og ansvarlig AI-brug er relevante?

**Afgrænsning:** Kun desktop- og server-pc-komponenter. Ingen priser eller køb. LLM'en fortolker og rangerer, mens kompatibiliteten altid afgøres af kode. Frontenden er sekundær.

## Eksamenskrav, der påvirker koden
- Læringsmålene vægter: **AI som udviklingsværktøj**, **vurdering og forbedring af AI-genereret kode**, **unit tests**, **kvalitetssikring** og **kritisk og ansvarlig brug af AI**.
- Formkrav: applikationen skal kunne **uploade data til clouden** (Azure foretrukket, localhost accepteret).
- Rapporten er højst 5 normalsider (12.000 anslag). Kode og bilag tæller ikke med. Koden og `docs/ai-log.md` er derfor det, der skal dokumentere arbejdet.
- Mundtlig eksamen: 5 min fremlæggelse og 5 min eksamination. Hele flowet skal kunne demonstreres hurtigt.

## Arbejdsregler for Claude Code
1. **Arbejd fase for fase** efter SPEC.md §11. **Stop efter hver fase**, opsummér hvad der er lavet, og vent på review før næste fase.
2. **Opdatér `docs/ai-log.md` efter hver fase** (format i SPEC.md §10). Vær ærlig om antagelser, usikkerheder og svage steder. Feltet "Review" udfylder den studerende selv. Lad det stå tomt.
3. Små, fokuserede commits pr. feature med beskrivende commit-beskeder.
4. Ingen test må kræve Ollama, MariaDB eller Azure. Brug fakes, mocks, SQLite og `LocalStorage`.
5. Kør `ruff check`, `ruff format` og `pytest` før du siger, at en fase er færdig.
6. Kode, identifiers og docstrings skrives på engelsk. `docs/`, README og ai-log skrives på dansk.
7. Ingen secrets i repoet. Nye env-variabler tilføjes til `.env.example`.
8. Er noget i specen uklart eller selvmodsigende, så **spørg** i stedet for at gætte.
9. Findes der allerede kode i repoet, så tilpas den til specen frem for at starte forfra, og forklar hvad du ændrer.

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
