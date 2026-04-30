FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api /app/apps/api

ARG LEGACY_APP_REPO=https://github.com/ytun1/NeoSmart-Hackathon-App.git
ARG LEGACY_APP_REV=0d066c1ddc963e562cc699a6a43f2d1e91c46828
RUN git clone --filter=blob:none "$LEGACY_APP_REPO" /app/NeoSmart-Hackathon-App \
    && cd /app/NeoSmart-Hackathon-App \
    && git checkout "$LEGACY_APP_REV" \
    && test -d backend \
    && rm -rf .git

WORKDIR /app/apps/api

RUN pip install --upgrade pip && pip install .

EXPOSE 10000

CMD ["/bin/sh", "-c", "mkdir -p \"${ARTIFACTS_ROOT:-/var/data/artifacts}\" && alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
