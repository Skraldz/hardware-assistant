FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "python -m app.bootstrap && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
