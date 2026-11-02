FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
# Diagnostic tools that need the real service names (ollama:11434, db:3306)
# to measure anything meaningful, so they have to run inside the container
# rather than on a host that may not even have a virtualenv.
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "python -m app.bootstrap && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
