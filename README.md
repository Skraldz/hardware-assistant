# Hardware Assistant

AI-drevet hardwareassistent og lagersystem. Se `SPEC.md` for den fulde tekniske spec og `CLAUDE.md` for projektrammerne. Eksamenskrav er opsummeret i `docs/exam-requirements.md`.

## Kør projektet

```bash
cp .env.example .env   # udfyld adgangskoder
docker compose up -d --build
```

Backend starter på `http://localhost:8000` (se `/docs` for OpenAPI). Databasen oprettes og seedes automatisk ved første opstart (tom database).

## Udvikling og tests (uden Docker)

Tests kører mod SQLite in-memory og kræver ikke MariaDB, Ollama eller Azure.

```bash
cd backend
pip install -e ".[dev]"
ruff check .
ruff format .
pytest --cov
```

## Status

Se `docs/ai-log.md` for en logget gennemgang af hver fase (hvad er genereret, antagelser, kendte risici, testdækning).
