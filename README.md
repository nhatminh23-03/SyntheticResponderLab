# SyntheticResponderLab

Premium Next.js + Python evolution of the Grounded Synthetic Respondent Lab.

This repository contains:
- a new **Next.js frontend** for the cinematic, one-page product experience
- a new **FastAPI backend** that wraps and preserves the working Python simulation logic
- the original **Streamlit prototype** kept as a reference implementation

The product helps a user:
- define a study mode
- define audience, product, market, and survey context
- configure an experiment
- run grounded synthetic respondent simulations
- inspect analysis, trust framing, and executive insights

## Repository Structure

```text
SyntheticResponderLab/
├── apps/
│   ├── api/                     # FastAPI backend for the new product
│   └── web/                     # Next.js frontend for the new product
├── Documentation/              # migration docs, specs, and implementation notes
├── UI Prototype/               # visual reference files
└── NeoSmart-Hackathon-App/     # legacy Streamlit app kept as reference
```

## Architecture

### `apps/web`
- Next.js 14
- Tailwind CSS
- Framer Motion
- premium one-page workflow UI

### `apps/api`
- FastAPI
- SQLAlchemy + Alembic
- SQLite for local development
- wraps legacy Python logic instead of rewriting it in JavaScript

### `NeoSmart-Hackathon-App`
- the original multipage Streamlit prototype
- kept in the repo as the reference logic source
- not the primary app to run for the new product

## Current Workflow

The current Next.js app includes:
- Main
- Study Mode
- Audience
- Product
- Market
- Survey
- Experiment
- Run Simulation
- Analysis
- Insights

## Prerequisites

- Node.js 18+
- npm
- Python 3.9+

## Quick Start

### 1. Backend

Create a local env file from the example:

```bash
cd apps/api
cp .env.example .env
```

Create the virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the migration:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn src.main:app --reload --port 8000
```

### 2. Frontend

Create a local frontend env file:

```bash
cd ../web
cp .env.example .env.local
```

Install dependencies and start the app:

```bash
npm install
npm run dev
```

Open:
- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## Environment

### Backend env

Use [`apps/api/.env.example`](apps/api/.env.example) as the template.

Important variables:
- `APP_ENV`
- `APP_DEBUG`
- `DATABASE_URL`
- `ARTIFACTS_ROOT`
- `LEGACY_APP_ROOT`
- `CORS_ALLOW_ORIGINS`

The backend now resolves relative paths from `apps/api/`. For local development, these values work:

```env
ARTIFACTS_ROOT=./artifacts
LEGACY_APP_ROOT=../../NeoSmart-Hackathon-App
```

Optional provider credentials:
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `GOOGLE_CLOUD_API_KEY`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH`
- `HUD_API_TOKEN`
- `ANTHROPIC_API_KEY`

### Frontend env

Use [`apps/web/.env.example`](apps/web/.env.example):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Testing

### Backend

```bash
cd apps/api
source .venv/bin/activate
pytest -q
```

### Frontend

```bash
cd apps/web
npm run test:unit
npm run build
```

## Important Notes Before Pushing To GitHub

- Do **not** commit local `.env` files.
- Do **not** commit local database files like `local-dev.db`.
- Do **not** commit generated artifacts under `apps/api/artifacts/`.
- Do **not** commit `node_modules/` or virtual environments.
- The root `.gitignore` in this repo is set up to ignore those.

One important security note:
- if you previously stored a real provider key in a local `.env`, rotate that key before publishing the repository if there is any chance it was ever exposed

## Legacy Reference App

The old Streamlit app lives in [`NeoSmart-Hackathon-App/`](NeoSmart-Hackathon-App/).

It remains useful for:
- validating behavior against the original prototype
- tracing legacy grounding, survey parsing, simulation, analysis, and insights logic
- understanding the migration history

The new product work should happen in:
- [`apps/api/`](apps/api/)
- [`apps/web/`](apps/web/)

## Suggested Git Setup

This workspace is not currently initialized as a git repository from the root.

If you want to publish from this root folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Documentation

Project planning and migration notes are in [`Documentation/`](Documentation/).

Key docs include:
- frontend migration review
- Next.js + Python migration plan
- Phase 0 backend spec
- Phase 1 backend implementation notes
- Phase 2 setup flow hardening notes
- Phase 3 chart system plan
