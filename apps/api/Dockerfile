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
# The legacy engine ships in-tree at apps/api/legacy_runtime and is used directly, so there is one
# copy for local development and production rather than two that can drift.
#
# The ACS prior tables are part of that tree. Persona generation catches a missing-priors error and
# substitutes heuristic profiles without failing, so an image built without them would quietly serve
# demo-shaped people while reporting success. Fail the build instead.
RUN test -d /app/apps/api/legacy_runtime/backend \
    && test -f /app/apps/api/legacy_runtime/data/processed/priors/age_income_priors.parquet

WORKDIR /app/apps/api

RUN pip install --upgrade pip && pip install .

EXPOSE 10000

CMD ["/bin/sh", "-c", "mkdir -p \"${ARTIFACTS_ROOT:-/var/data/artifacts}\" && alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
