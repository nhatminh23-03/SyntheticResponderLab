FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api /app/apps/api
COPY NeoSmart-Hackathon-App /app/NeoSmart-Hackathon-App

WORKDIR /app/apps/api

RUN pip install --upgrade pip && pip install .

EXPOSE 10000

CMD ["/bin/sh", "-c", "mkdir -p \"${ARTIFACTS_ROOT:-/var/data/artifacts}\" && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
