# PROGRESS.md -- B10 Union Woodworking Quote Engine

Tracks what has been built, what's working, and what's next.
Last updated: 2026-02-16

---

## Phase 0: Legacy ML System (v1)

The original system lives in `src/` and uses float arithmetic, static cost tables,
and a CatBoost regression model. It is **not** the production system.

| Component | File | Status |
|-----------|------|--------|
| Data ingestion (Excel profitability reports) | `src/data/ingest_profitability.py` | Done |
| Data preparation / train-test splits | `src/data/prepare_data.py` | Done |
| Schema definitions | `src/data/schema.py` | Done |
| Deterministic should-cost model (float-based) | `src/models/should_cost.py` | Done |
| CatBoost ML adjuster | `src/models/ml_adjuster.py` | Done |
| Combined quote engine (v1) | `src/models/quote_engine.py` | Done |
| FastAPI v1 endpoints | `src/api/main.py` | Done |
| Web UI (vanilla HTML) | `src/web/index.html` | Done |
| Static cost tables | `config/cost_tables.json` | Done |

**Limitations of v1**: Float arithmetic for money, no effective dating,
no snapshots, no audit trail, no auth, no reproducibility guarantees.

---

## Phase 1: Production Backend (v2) -- Core Infrastructure

Full rewrite using Decimal math, SQLAlchemy 2.0, effective-dated pricing,
snapshot-based reproducibility, and role-based auth.

### Database & Models

| Component | File | Status |
|-----------|------|--------|
| SQLAlchemy Base + engine setup | `backend/app/database.py` | Done |
| App configuration (Pydantic Settings) | `backend/app/config.py` | Done |
| User model (roles: admin, estimator, viewer) | `backend/app/models/user.py` | Done |
| Customer model (soft-delete) | `backend/app/models/customer.py` | Done |
| Project model (customer FK) | `backend/app/models/project.py` | Done |
| Material catalog (effective-dated, NUMERIC) | `backend/app/models/catalog.py` | Done |
| PriceBookSnapshot (JSONB + SHA-256 hash) | `backend/app/models/price_book.py` | Done |
| Quote model (status flow, tier pricing, JSONB) | `backend/app/models/quote.py` | Done |
| Tracking models (LostQuote, CompletedProject, NegotiationHistory) | `backend/app/models/tracking.py` | Done |
| Audit log (append-only) | `backend/app/models/audit.py` | Done |
| Market index models (4 tables -- see Phase 2) | `backend/app/models/market_index.py` | Done |
| Initial migration (all core tables) | `backend/alembic/versions/cf15da76d787_initial_schema.py` | Done |
| Market index migration (4 new + 2 extended) | `backend/alembic/versions/a1b2c3d4e5f6_add_market_index_tables.py` | Done |

### Pure Quoting Engine (`backend/app/engine/`)

| Component | File | Status |
|-----------|------|--------|
| Frozen dataclasses (QuoteParams, CostBreakdown) | `backend/app/engine/types.py` | Done |
| PriceBook (immutable, from_snapshot_data, SHA-256) | `backend/app/engine/price_book.py` | Done |
| Cost calculator (pure functions, Decimal only) | `backend/app/engine/cost_calculator.py` | Done |
| Quote generator (3-tier pricing, confidence, risk) | `backend/app/engine/quote_generator.py` | Done |
| Snapshot bridge (DB-aware, creates PriceBookSnapshot) | `backend/app/engine/snapshot.py` | Done |
| MarketMultipliers (frozen dataclass, pure adjustments) | `backend/app/engine/market_adjuster.py` | Done |

### Auth

| Component | File | Status |
|-----------|------|--------|
| Password hashing (bcrypt) | `backend/app/auth/password.py` | Done |
| JWT creation / decoding | `backend/app/auth/jwt.py` | Done |
| Auth dependencies (require_admin, require_estimator_or_admin) | `backend/app/auth/dependencies.py` | Done |

### Pydantic Schemas

| Component | File | Status |
|-----------|------|--------|
| Auth schemas (login, token, user CRUD) | `backend/app/schemas/auth.py` | Done |
| Catalog schemas (material, price book) | `backend/app/schemas/catalog.py` | Done |
| Customer schemas (create, update, response) | `backend/app/schemas/customer.py` | Done |
| Quote schemas (create, response, list) | `backend/app/schemas/quote.py` | Done |
| Tracking schemas (lost quote, completed project) | `backend/app/schemas/tracking.py` | Done |

### API Routers

| Component | File | Status |
|-----------|------|--------|
| Auth endpoints (register, login) | `backend/app/routers/auth.py` | Done |
| Catalog endpoints (materials, price books) | `backend/app/routers/catalog.py` | Done |
| Customer CRUD endpoints | `backend/app/routers/customers.py` | Done |
| Quote endpoints (create, compute, send, accept) | `backend/app/routers/quotes.py` | Done |
| Tracking endpoints (lost quotes, completed projects) | `backend/app/routers/tracking.py` | Done |

### Services (DB-aware business logic)

| Component | File | Status |
|-----------|------|--------|
| Auth service (user CRUD, login) | `backend/app/services/auth_service.py` | Done |
| Audit service (append-only logging) | `backend/app/services/audit_service.py` | Done |
| Catalog service (effective-dated material CRUD) | `backend/app/services/catalog_service.py` | Done |
| Customer service (soft-delete CRUD) | `backend/app/services/customer_service.py` | Done |
| Quote service (full lifecycle orchestration) | `backend/app/services/quote_service.py` | Done |
| Tracking service (lost quotes, project completion) | `backend/app/services/tracking_service.py` | Done |
| Market service (DB-to-engine bridge) | `backend/app/services/market_service.py` | Done |

### Utilities

| Component | File | Status |
|-----------|------|--------|
| Decimal utilities (to_decimal, round_money) | `backend/app/utils/decimal_utils.py` | Done |
| PDF generator (WeasyPrint) | `backend/app/pdf/generator.py` | Done |

### Tests

| Component | File | Status |
|-----------|------|--------|
| Test configuration (SQLite, JSONB/UUID compat) | `backend/tests/conftest.py` | Done |
| Engine unit tests (board feet, margins) | `backend/tests/unit/test_engine.py` | Needs update (old PriceBook constructor) |
| Auth unit tests (hashing, JWT) | `backend/tests/unit/test_auth.py` | Partial (2 JWT tests fail on config) |
| Market adjuster unit tests (22 tests) | `backend/tests/unit/test_market_adjuster.py` | All 22 pass |
| Catalog API integration tests | `backend/tests/integration/test_catalog_api.py` | Needs update |
| Quotes API integration tests | `backend/tests/integration/test_quotes_api.py` | Needs update |

### Seed Scripts

| Component | File | Status |
|-----------|------|--------|
| Core seed data (admin user, materials, snapshot) | `backend/scripts/seed_data.py` | Done |
| DB bootstrap helper | `backend/scripts/seed_db.py` | Done |
| Market data seed (JSONL + multiplier rules) | `backend/scripts/seed_market_data.py` | Done |

### Placeholder Packages (scaffolded, not implemented yet)

| Package | Purpose | Status |
|---------|---------|--------|
| `backend/app/integrations/` | Monday.com, QuickBooks, TSheets, Google Drive | Scaffolded |
| `backend/app/labor/` | Employee profiles, scheduling, reports | Scaffolded |
| `backend/app/ml/` | CatBoost ML module (port from v1) | Scaffolded |

---

## Phase 2: Market-Indexed Pricing System

Converts static cost tables into an effective-dated pricing engine aligned
to live market conditions. Implemented 2026-02-16.

### Architecture

```
  JSONL Data Pack              Market DB Tables              Pure Engine
  (external data)              (effective-dated)             (frozen dataclass)
 +-----------------+      +------------------------+     +---------------------+
 | lumber prices   | ---> | market_index_series     | --> | MarketMultipliers   |
 | labor benchmarks|      | market_index_observations|    |  material_mults {}  |
 | fuel prices     |      | multiplier_rules        |    |  labor_mult         |
 | demand signals  |      | multiplier_snapshots    |    |  fuel_surcharge     |
 | hardware SKUs   |      +------------------------+     |  demand_premium     |
 | freight rates   |             |                        |  powder_coat_mult   |
 | sub benchmarks  |             v                        +---------------------+
 +-----------------+      market_service.py                       |
                          (DB -> engine bridge)                   v
                                                          cost_calculator.py
                                                          (pure, no I/O)
```

### Multiplier Formulas

| Multiplier | Formula | Example |
|-----------|---------|---------|
| Material Index | current_price / baseline_price | Walnut HMR $3.575 / baseline $3.00 = 1.192x |
| Labor | ECI_current / ECI_baseline | $21.67/hr / $20.00 baseline = 1.084x |
| Fuel Surcharge | current_diesel / baseline_diesel | $3.688 / $3.50 = 1.054x |
| Demand Premium | f(Dodge Momentum Index delta) | DMI 296.8 / 250 baseline = 1.187x |

### New Database Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `market_index_series` | What we track (data series definitions) | dataset, category, name, unit, source, species, grade, geo |
| `market_index_observations` | Each data point (effective-dated) | series_id FK, observed_date, value_numeric NUMERIC(14,6), value_json JSONB |
| `multiplier_rules` | How indexes become multipliers | series_id FK, domain, formula, baseline_value, floor_mult, ceiling_mult |
| `multiplier_snapshots` | Frozen multipliers at quote-send time | rule_id FK, snapshot_date, baseline_value, current_value, multiplier |

### Extended Existing Tables

| Table | New Columns | Purpose |
|-------|-------------|---------|
| `price_book_snapshots` | `market_multipliers JSONB` | Store frozen market state alongside price book |
| `quotes` | `market_snapshot_date DATE`, `market_adjusted_cost NUMERIC(12,2)` | Track market-adjusted cost separately |

### Engine Changes

| Change | Detail |
|--------|--------|
| New `MarketMultipliers` frozen dataclass | Immutable, serializable, SHA-256 hashable |
| 5 pure adjustment functions | `apply_material_market_adjustment`, `apply_labor_market_adjustment`, `apply_fuel_surcharge`, `apply_powder_coating_adjustment`, `apply_demand_premium` |
| `calculate_total_cost()` extended | New optional `market` parameter (backward compatible) |
| Material cost | Adjusted by species:grade market multiplier |
| All labor departments | Adjusted by labor multiplier |
| Delivery cost | Adjusted by fuel surcharge factor |
| Powder coating | Adjusted by powder coating multiplier |

### Data Ingestion

| Component | Detail |
|-----------|--------|
| JSONL loader | Parses 9 dataset types, comment-aware, upsert logic |
| Data pack | 27 records: lumber (wholesale + retail), labor (BLS), finishing, hardware, freight, fuel, demand, subcontractor |
| Seed script | Loads JSONL, creates multiplier rules with baselines from cost_tables.json |

### 9 Supported Dataset Types

1. `lumber_price` (softwood framing, hardwood wholesale, hardwood retail)
2. `labor_benchmark` (BLS median wages, percentile data)
3. `labor_burden` (ECEC burden rates)
4. `finish_cost_benchmark` (powder coating ranges)
5. `hardware_price` (SKU-level pricing with volume tiers)
6. `freight_rate` (spot/contract linehaul rates)
7. `fuel_price_index` (EIA weekly diesel)
8. `construction_demand_signal` (Dodge Momentum Index)
9. `subcontractor_benchmark` (CNC shop rates)

### Data Sources for Periodic Ingestion

| Category | Source | Frequency |
|----------|--------|-----------|
| Softwood lumber | Random Lengths, NAHB, Madison's | Weekly |
| Hardwood wholesale | Hardwood Market Report (HMR) | Weekly/biweekly |
| Hardwood retail | Woodworkers Source, Bell Forest Products | Dynamic |
| Sheet goods | Forest2Market, TradingEconomics | Monthly/daily |
| Labor wages | BLS OEWS | Annual |
| Labor burden | BLS ECI, BLS ECEC | Quarterly |
| Installed millwork | RSMeans (Gordian) | Annual |
| Finishing/coatings | Sherwin-Williams, PPG, AWMAC | Quarterly |
| Hardware | Hafele, Richelieu, CabinetParts, McMaster-Carr | Live catalog |
| Freight | DAT, FreightWaves, uShip | Weekly/daily |
| Fuel | EIA, AAA Gas Prices, GasBuddy | Weekly/daily |
| Construction demand | Dodge, ABC Confidence Index, FRED | Monthly |

### Test Coverage (Phase 2)

22 unit tests -- all passing:

- `TestMarketMultipliersConstruction` (5 tests): identity, frozen, exact/fallback/missing lookups
- `TestSerialization` (3 tests): dict round-trip, deterministic SHA-256
- `TestAdjustmentFunctions` (8 tests): each function with and without market data
- `TestCalculateTotalCostWithMarket` (6 tests): backward compat, identity = none, market increases cost, adjusts material/labor/delivery

---

## What's Next

### Immediate (test fixes)

- [ ] Update `test_engine.py` to use `PriceBook.from_snapshot_data()` constructor
- [ ] Fix `test_auth.py` JWT config issues (2 tests)
- [ ] Update integration tests for new schema columns

### Short-term (complete market system)

- [ ] Add API endpoint: `POST /api/v1/market/ingest` (upload JSONL data pack)
- [ ] Add API endpoint: `GET /api/v1/market/multipliers` (current multiplier values)
- [ ] Add API endpoint: `GET /api/v1/market/series` (list tracked series)
- [ ] Wire `market_service.build_market_multipliers()` into `quote_service` flow
- [ ] Create Pydantic schemas for market data responses
- [ ] Add market snapshot freezing to quote-send workflow
- [ ] Run `seed_market_data.py` against live PostgreSQL to verify end-to-end

### Medium-term (ingestion automation)

- [ ] Build scheduled scraper for EIA diesel prices (weekly cron)
- [ ] Build scheduled scraper for BLS wage data (annual)
- [ ] Build manual import tool for HMR hardwood prices (subscription data)
- [ ] Add data staleness alerts (warn if observations > expected frequency)
- [ ] Add multiplier drift dashboard (show current vs baseline)

### Phase 3: Frontend (Next.js 14)

- [ ] Quote builder wizard (mobile-first)
- [ ] Customer management pages
- [ ] Catalog / price book admin
- [ ] Market data dashboard
- [ ] Quote PDF preview and download

### Phase 4: Integrations

- [ ] Monday.com (project management sync)
- [ ] QuickBooks (invoicing)
- [ ] TSheets (labor time tracking)
- [ ] Google Drive (document storage)

### Phase 5: ML Enhancement

- [ ] Port CatBoost model from v1 to v2 architecture
- [ ] Train on historical quote data with market features
- [ ] Add ML confidence score alongside deterministic quote
- [ ] A/B test ML-adjusted vs deterministic-only pricing

---

## Architecture Invariants (enforced)

1. Engine purity: `backend/app/engine/` has zero imports from `app.models` or `app.database`
2. Decimal money: no `float` in any monetary calculation
3. Snapshot reproducibility: same PriceBook + MarketMultipliers + QuoteParams = same CostBreakdown
4. Effective dating: all cost/rate tables have valid_from / valid_until
5. Append-only audit: audit_log rows are never updated or deleted
6. Quote locking: accepted quotes are immutable
7. Market multipliers clamped: floor_mult <= multiplier <= ceiling_mult
8. Backward compatibility: `market=None` in `calculate_total_cost()` produces pre-market results

---

## File Inventory

### Backend Application (53 files)

```
backend/app/
  __init__.py
  config.py                          # Pydantic Settings
  database.py                        # SQLAlchemy engine + session
  main.py                            # FastAPI app + CORS + startup
  auth/
    __init__.py
    dependencies.py                  # require_admin, require_estimator_or_admin
    jwt.py                           # create_token, decode_token
    password.py                      # hash_password, verify_password
  engine/
    __init__.py                      # Exports all engine types + functions
    cost_calculator.py               # Pure cost calculations (Decimal)
    market_adjuster.py               # MarketMultipliers + adjustment functions
    price_book.py                    # PriceBook frozen dataclass
    quote_generator.py               # 3-tier quote generation
    snapshot.py                      # DB bridge for PriceBookSnapshot
    types.py                         # QuoteParams, CostBreakdown dataclasses
  ingestion/
    __init__.py
    jsonl_loader.py                  # JSONL data pack loader (9 dataset types)
  integrations/__init__.py           # Placeholder
  labor/__init__.py                  # Placeholder
  ml/__init__.py                     # Placeholder
  models/
    __init__.py                      # Imports all models for Alembic
    audit.py                         # AuditLog
    catalog.py                       # Material, MaterialCostHistory
    customer.py                      # Customer
    market_index.py                  # MarketIndexSeries, Observations, Rules, Snapshots
    price_book.py                    # PriceBookSnapshot
    project.py                       # Project
    quote.py                         # Quote, QuoteStatus
    tracking.py                      # LostQuote, CompletedProject, NegotiationHistory
    user.py                          # User, UserRole
  pdf/
    __init__.py
    generator.py                     # WeasyPrint PDF generation
  routers/
    __init__.py
    auth.py                          # POST /register, /login
    catalog.py                       # GET/PUT materials, snapshots
    customers.py                     # CRUD customers
    quotes.py                        # Full quote lifecycle
    tracking.py                      # Lost quotes, completed projects
  schemas/
    __init__.py
    auth.py
    catalog.py
    customer.py
    quote.py
    tracking.py
  services/
    __init__.py
    audit_service.py
    auth_service.py
    catalog_service.py
    customer_service.py
    market_service.py                # DB -> MarketMultipliers bridge
    quote_service.py
    tracking_service.py
  utils/
    __init__.py
    decimal_utils.py                 # to_decimal, round_money
```

### Tests (6 test files + conftest)

```
backend/tests/
  conftest.py                        # SQLite test DB, JSONB/UUID compat
  unit/
    test_engine.py                   # Needs update (old constructor)
    test_auth.py                     # 4/6 passing
    test_market_adjuster.py          # 22/22 passing
  integration/
    test_catalog_api.py              # Needs update
    test_quotes_api.py               # Needs update
```

### Migrations (2)

```
backend/alembic/versions/
  cf15da76d787_initial_schema.py     # All core tables
  a1b2c3d4e5f6_add_market_index_tables.py  # 4 market tables + 2 extended
```

### Scripts (3)

```
backend/scripts/
  seed_data.py                       # Admin user, materials, snapshot
  seed_db.py                         # DB bootstrap helper
  seed_market_data.py                # JSONL ingestion + multiplier rules
```

### Data

```
data/
  market_data_pack_2026_02.jsonl     # 27 records across 7 categories
  *.xlsx                             # Historical profitability reports
  *.txt                              # Text exports of profitability reports
```

### Infrastructure

```
docker-compose.yml                   # PostgreSQL 16 + backend + frontend
.env.example                         # Environment variable template
Dockerfile                           # Backend container
backend/alembic.ini                  # Migration config
backend/pyproject.toml               # Python project config
```
