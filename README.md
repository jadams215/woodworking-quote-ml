# Woodworking Quote Engine

Production-grade quoting system for [B10 Union, LLC](https://www.b-10union.com/) — a custom furniture design and fabrication company based in Atlanta, GA. Combines a deterministic cost model with market-indexed pricing and optional ML adjustments to generate accurate, reproducible, three-tier quotes for woodworking projects.

## Highlights

- **Deterministic Pricing Engine** — Pure functions, zero side effects, 100% Decimal math (never float)
- **Market-Indexed Costs** — Material, labor, fuel, and demand multipliers sourced from real market data
- **Three-Tier Quotes** — Value, Standard, and Premium pricing with configurable margins
- **Quote Reproducibility** — SHA-256 price book snapshots guarantee any quote can be recreated exactly
- **Effective-Dated Catalog** — Additive-only pricing history; no retroactive changes
- **Audit Trail** — Every mutation logged with who, what, when, and before/after values
- **Role-Based Access** — Admin, Estimator, and Viewer roles via JWT authentication
- **PDF Generation** — Professional quote PDFs with WeasyPrint
- **26 REST API Endpoints** — Full OpenAPI documentation at `/docs`
- **ML Adjustment Layer** — Optional CatBoost model learns pricing patterns from historical data

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐
│  Frontend    │────▶│  FastAPI (v2 API) │────▶│  PostgreSQL 16    │
│  Next.js 14  │     │  26 endpoints     │     │  13 tables        │
└──────────────┘     └────────┬─────────┘     └───────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Pure Engine        │ ← No I/O, no DB imports
                    │  Decimal math only  │
                    │  Frozen dataclasses │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        Cost Calculator   Market Adjuster   Quote Generator
        (board feet,      (multipliers,     (3 tiers, confidence,
         materials,        fuel surcharge,   risk flags)
         labor, delivery)  demand premium)
```

### Key Design Principles

1. **Engine purity** — `backend/app/engine/` has zero imports from `app.models` or `app.database`
2. **Money = Decimal** — Every monetary field, calculation, and DB column uses `Decimal` / `NUMERIC`
3. **Snapshot reproducibility** — Same `PriceBook` + `MarketMultipliers` + `QuoteParams` = same result, always
4. **Effective dating** — All cost and rate tables carry `effective_from` / `effective_to`
5. **Append-only audit** — `audit_log` rows are never updated or deleted
6. **Quote locking** — Accepted quotes are immutable; edits create new revisions
7. **Market backward compatibility** — `market=None` produces pre-market results

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 (SQLite for development) |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Auth | JWT (HS256) + bcrypt password hashing |
| PDF | WeasyPrint + Jinja2 templates |
| ML (optional) | CatBoost regression |
| Infrastructure | Docker Compose |

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for PostgreSQL)
- Node.js 18+ (frontend, optional)

### 1. Clone and install

```bash
git clone https://github.com/your-org/woodworking-quote-ml.git
cd woodworking-quote-ml

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install backend
cd backend
pip install -e ".[dev]"
```

### 2. Start the database

```bash
# From project root
docker compose up db -d
```

### 3. Run migrations and seed data

```bash
cd backend
alembic upgrade head
python scripts/seed_data.py
python scripts/seed_market_data.py  # Optional: market-indexed pricing
```

### 4. Start the backend

```bash
cd backend
uvicorn app.main:app --reload
```

API available at http://localhost:8000 — docs at http://localhost:8000/docs

### 5. Start the frontend (optional)

```bash
cd frontend
npm install
npm run dev
```

Frontend available at http://localhost:3000

### All-in-one with Docker Compose

```bash
docker compose up
```

## API Endpoints

### Authentication

```
POST   /api/v2/auth/login          Login (OAuth2 password flow → JWT)
POST   /api/v2/auth/register       Create user (admin only)
GET    /api/v2/auth/me             Current user info
```

### Quotes

```
POST   /api/v2/quotes              Create and compute a quote
GET    /api/v2/quotes              List quotes (filter by customer, status)
GET    /api/v2/quotes/{id}         Get quote by ID
POST   /api/v2/quotes/{id}/reproduce   Verify quote reproducibility
GET    /api/v2/quotes/{id}/pdf     Download quote as PDF
```

### Customers

```
POST   /api/v2/customers           Create customer
GET    /api/v2/customers           List customers (paginated)
GET    /api/v2/customers/{id}      Get customer
PUT    /api/v2/customers/{id}      Update customer
DELETE /api/v2/customers/{id}      Soft-delete customer (admin)
```

### Catalog

```
GET    /api/v2/catalog/materials             Active material costs
PUT    /api/v2/catalog/materials/{s}/{g}     Update cost (admin, creates new effective-dated row)
GET    /api/v2/catalog/labor-rates           Active labor rates
GET    /api/v2/catalog/snapshot/current      Current price book snapshot
```

### Tracking & Analytics

```
POST   /api/v2/tracking/lost-quotes            Record a lost quote
GET    /api/v2/tracking/lost-quotes/insights   Aggregated loss insights
POST   /api/v2/tracking/completed-projects     Record project completion
GET    /api/v2/tracking/project-insights       Project analytics
```

### Health

```
GET    /health    Health check (no auth required)
```

### Example: Generate a Quote

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v2/auth/login \
  -d "username=admin@b10union.com&password=admin123" | jq -r .access_token)

# Create a quote
curl -X POST http://localhost:8000/api/v2/quotes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "wood_species": "White Oak",
    "material_grade": "Standard",
    "length_in": "96.00",
    "width_in": "42.00",
    "height_in": "1.50",
    "quantity": 1,
    "has_woodwork": true,
    "woodwork_hours": "40.00",
    "finishing_complexity": 3,
    "delivery_miles": 25
  }'
```

## Project Structure

```
woodworking-quote-ml/
├── backend/
│   ├── app/
│   │   ├── auth/               # JWT + bcrypt authentication
│   │   ├── engine/             # Pure quoting engine (no I/O)
│   │   │   ├── types.py        # Frozen dataclasses (QuoteParams, CostBreakdown)
│   │   │   ├── price_book.py   # Immutable PriceBook + SHA-256 hashing
│   │   │   ├── cost_calculator.py  # Pure cost functions (Decimal only)
│   │   │   ├── market_adjuster.py  # MarketMultipliers + adjustment functions
│   │   │   ├── quote_generator.py  # 3-tier quote generation
│   │   │   └── snapshot.py     # DB bridge (only engine file with SQLAlchemy)
│   │   ├── models/             # SQLAlchemy ORM (8 model files, 13 tables)
│   │   ├── schemas/            # Pydantic v2 request/response schemas
│   │   ├── routers/            # FastAPI route handlers (26 routes)
│   │   ├── services/           # Business logic layer (DB-aware)
│   │   ├── ingestion/          # JSONL market data loader (9 dataset types)
│   │   ├── pdf/                # WeasyPrint PDF generation
│   │   ├── ml/                 # Optional CatBoost ML module
│   │   ├── integrations/       # Monday.com, QuickBooks, TSheets (scaffolded)
│   │   └── labor/              # Employee profiles, scheduling (scaffolded)
│   ├── scripts/                # Seed data, market data loader
│   ├── tests/                  # Unit + integration tests
│   ├── alembic/                # Database migrations
│   └── pyproject.toml
├── frontend/                   # Next.js 14 app (planned)
├── data/                       # JSONL data packs, profitability reports
├── config/                     # Cost tables (JSON)
├── docker-compose.yml
└── .env.example
```

## Market-Indexed Pricing

The system adjusts base prices using real market data, ingested as JSONL data packs:

| Multiplier | Formula | Example |
|-----------|---------|---------|
| Material | current_price / baseline_price | Walnut $3.575 / $3.00 baseline = 1.192x |
| Labor | ECI_current / ECI_baseline | $21.67/hr / $20.00 = 1.084x |
| Fuel Surcharge | current_diesel / baseline_diesel | $3.688 / $3.50 = 1.054x |
| Demand Premium | f(Dodge Momentum Index) | DMI 296.8 / 250 = 1.187x |

### Supported Data Sources

9 dataset types covering lumber prices (wholesale + retail), BLS labor benchmarks, fuel indices, construction demand signals, hardware SKU pricing, freight rates, finishing benchmarks, and subcontractor rates.

Multipliers are clamped between configurable floor and ceiling values and frozen at quote-send time for reproducibility.

## Testing

```bash
cd backend

# Run all tests
pytest -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Specific test
pytest tests/unit/test_engine.py::test_generate_quote_reproducibility -v

# With coverage
pytest --cov=app --cov-report=html
```

### Test Coverage

- **Engine unit tests** (11 tests) — Board feet, material/labor/delivery costs, margins, reproducibility, SHA-256 determinism, risk flags, confidence scoring
- **Auth unit tests** (7 tests) — Bcrypt hashing, JWT lifecycle, token expiry/tampering
- **Market adjuster tests** (22 tests) — Construction, serialization, adjustment functions, backward compatibility
- **Integration tests** — Full API flow (login → create customer → quote → reproduce)

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and update:

```env
# Required
DATABASE_URL=postgresql://user:password@host:5432/dbname
JWT_SECRET_KEY=<generate-256-bit-random-string>

# Optional
ML_ENABLED=false
PDF_COMPANY_NAME=B10 Union, LLC
```

See [.env.example](.env.example) for all available settings.

### Cost Tables

Base material costs, labor rates, and overhead configuration are stored in `config/cost_tables.json` and seeded into the database as effective-dated records. Updates are made through the API (admin only) and automatically create new price book snapshots.

## Deployment

### Production Checklist

- [ ] Set `JWT_SECRET_KEY` to a cryptographically random 256-bit string
- [ ] Change the default admin password (`admin123`)
- [ ] Set `DATABASE_URL` to a production PostgreSQL instance
- [ ] Update CORS allowed origins in `main.py`
- [ ] Enable HTTPS/TLS (nginx reverse proxy recommended)
- [ ] Configure database backups
- [ ] Set up log monitoring and alerting
- [ ] Add rate limiting middleware ([slowapi](https://github.com/laurentS/slowapi))

### Docker Production

```bash
docker compose up -d
```

The compose file runs PostgreSQL 16, the FastAPI backend, and the Next.js frontend with health checks and automatic restarts.

## Security

A full OWASP Top 10 security review is documented in [backend/SECURITY_REVIEW.md](backend/SECURITY_REVIEW.md).

**Implemented:**
- Decimal-only money (no float rounding exploits)
- JWT + bcrypt authentication with role-based access control
- SQL injection prevention via SQLAlchemy ORM
- Input validation at API boundary (Pydantic)
- Comprehensive audit logging
- Soft deletes (no data loss)

**Recommended for production:**
- Rate limiting (brute force protection)
- MFA (multi-factor authentication)
- CSP headers
- Session revocation

## Development

```bash
# Format
black backend/app/ --line-length 100
isort backend/app/ --profile black

# Lint
ruff check backend/app/

# Commit style
# feat: add new feature
# fix: fix a bug
# refactor: code restructuring
# test: add or update tests
```

## Roadmap

### Completed

- [x] V2 backend rewrite (Decimal math, pure engine, effective dating)
- [x] JWT authentication with role-based access control
- [x] 26 REST API endpoints with OpenAPI docs
- [x] PDF quote generation
- [x] Market-indexed pricing system (9 dataset types)
- [x] Comprehensive audit trail
- [x] Unit + integration test suites
- [x] OWASP security review

### In Progress

- [ ] Wire market multipliers into live quote flow
- [ ] Market data API endpoints (ingest, query, multiplier dashboard)
- [ ] Fix remaining test failures (engine constructor, JWT config)

### Planned

- [ ] **Frontend** — Next.js 14 quote builder wizard, catalog admin, analytics dashboard
- [ ] **Integrations** — Monday.com, QuickBooks, TSheets, Google Drive
- [ ] **ML Enhancement** — Retrain CatBoost with market features, prediction intervals
- [ ] **Mobile** — Offline-first quote builder for job site use
- [ ] **Advanced Analytics** — Margin trends, win rates, cost variance tracking

## V1 Legacy System

The original ML prototype lives in `src/` and uses float arithmetic, static cost tables, and a CatBoost regression model. It is preserved for reference but is **not** the production system. The V2 backend in `backend/` is a complete rewrite addressing all V1 limitations.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Author

James Adams — Building practical ML tools for small business operations.
