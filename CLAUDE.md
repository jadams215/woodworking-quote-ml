# CLAUDE.md — Woodworking Quoting App

## Project Overview
Production-grade woodworking quoting application for B10 Union LLC.
Deterministic pricing engine with optional ML suggestions.

## Tech Stack
- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic
- Database: PostgreSQL 16
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS
- Auth: JWT (email/password)
- ML (optional): CatBoost regression
- PDF: WeasyPrint

## Key Architecture Rules
1. Quoting engine (`backend/app/engine/`) is PURE FUNCTIONS — no DB calls, no side effects
2. All money values use Python Decimal, never float
3. Every quote stores `input_snapshot_json` + `calc_snapshot_json` for reproducibility
4. Material prices and labor rates are effective-dated (no hardcoded costs)
5. Missing prices emit warnings; never silently use $0
6. Quote status flow: draft → computed → sent → accepted → rejected
7. Accepted quotes are locked — edits create new revisions
8. Engine module NEVER imports from `app.models` or `app.database`
9. Market multipliers are optional — `market=None` means no adjustment (backward compatible)
10. Multiplier snapshots are frozen at quote-send time for reproducibility

## Directory Structure
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/schemas/` — Pydantic v2 request/response schemas
- `backend/app/routers/` — FastAPI route handlers
- `backend/app/services/` — Business logic (DB-aware, orchestrates engine + persistence)
- `backend/app/engine/` — Pure deterministic quoting engine (Decimal math)
- `backend/app/engine/market_adjuster.py` — MarketMultipliers frozen dataclass + pure adjustment functions
- `backend/app/ingestion/` — Market data ingestion (JSONL loader for 9 dataset types)
- `backend/app/auth/` — JWT authentication
- `backend/app/ml/` — Optional CatBoost ML module
- `backend/app/pdf/` — WeasyPrint PDF generation
- `backend/app/integrations/` — Monday.com, QuickBooks, TSheets, Google Drive
- `backend/app/labor/` — Employee profiles, scheduling, reports
- `backend/tests/` — pytest tests (unit/ and integration/)
- `frontend/src/app/` — Next.js App Router pages
- `frontend/src/components/` — React components
- `data/` — JSONL data packs + historical profitability reports

## Commands
- Start DB: `docker compose up db`
- Backend dev: `cd backend && uvicorn app.main:app --reload`
- Frontend dev: `cd frontend && npm run dev`
- Migrations: `cd backend && alembic upgrade head`
- New migration: `cd backend && alembic revision --autogenerate -m "description"`
- Tests: `cd backend && pytest -v`
- Seed data: `cd backend && python scripts/seed_data.py`
- Seed market data: `cd backend && python scripts/seed_market_data.py`
- All services: `docker compose up`

## Progress Tracking
See `PROGRESS.md` for full implementation status, file inventory, and what's next.

## Testing Requirements
- All engine functions must have unit tests
- Test reproducibility: same inputs + rule version → same output hash
- Integration test: full quote lifecycle (create → compute → accept → locked)
- Use SQLite in-memory for test DB (see `tests/conftest.py`)

## Style
- Python: Black formatter (100 line length), isort, ruff
- TypeScript: Prettier, ESLint
- Commits: conventional commits (feat:, fix:, refactor:, test:)
