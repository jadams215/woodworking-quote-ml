# Woodworking Quote Engine

Real-time quote generation system for woodworking projects, combining deterministic cost modeling with machine learning adjustments.

## Features

- **Deterministic Cost Model** (`should_cost.py`): Bottom-up cost calculation based on materials, labor, overhead, and delivery
- **ML Adjustment Model**: CatBoost regression model learns pricing patterns from historical data
- **Three-Tier Pricing**: Generates Value, Standard (recommended), and Premium pricing options
- **Confidence Scoring**: Provides confidence levels and risk flags for each quote
- **Lost Quote Tracking**: Record and analyze quotes lost to competitors for pricing insights
- **Project Completion Tracking**: Compare quoted vs actual costs to improve future estimates
- **REST API**: FastAPI backend with full OpenAPI documentation
- **Web UI**: Simple web interface for quote generation

## Quick Start

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd woodworking-quote-ml

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run the Application

```bash
# Start the API server with web UI
python run.py

# Or specify host/port
python run.py --host 127.0.0.1 --port 8080
```

Then open http://localhost:8000 in your browser.

### API Documentation

With the server running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
woodworking-quote-ml/
├── src/
│   ├── api/              # FastAPI application
│   │   ├── main.py       # API endpoints
│   │   └── cache.py      # Request caching
│   ├── data/             # Data processing
│   │   ├── ingest_profitability.py
│   │   ├── prepare_data.py
│   │   └── schema.py
│   ├── models/           # ML and cost models
│   │   ├── should_cost.py      # Deterministic cost model
│   │   ├── ml_adjuster.py      # CatBoost ML model
│   │   ├── quote_engine.py     # Combined quote generation
│   │   └── validate_should_cost.py
│   └── web/              # Web UI
│       └── index.html
├── config/
│   └── cost_tables.json  # Configurable pricing tables
├── data/
│   ├── processed/        # Prepared training data
│   └── validation/       # Model validation results
├── models/               # Trained ML models
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── run.py               # Convenience runner script
```

## Data Pipeline

### 1. Ingest Source Data

Parse profitability reports from Excel/text files:

```bash
python run.py --ingest
```

### 2. Prepare Training Data

Create train/validation/test splits:

```bash
python run.py --prepare-data
```

### 3. Train ML Model

Train the CatBoost adjustment model:

```bash
python run.py --train
```

### 4. Validate Model

Compare should-cost predictions to actuals:

```bash
python run.py --validate
```

## API Endpoints

### Quote Generation

```bash
# Generate a quote
POST /api/v1/quotes/generate
{
  "project_name": "Custom Cabinet",
  "wood_species": "Maple",
  "material_grade": "Premium",
  "length_in": 80,
  "width_in": 24,
  "height_in": 36,
  "quantity": 2,
  "estimated_labor_hours": 12,
  "finishing_complexity": 4,
  "delivery_miles": 15,
  "installation_required": true
}
```

### Lost Quotes

```bash
# Record a lost quote
POST /api/v1/quotes/lost
{
  "quote_id": "Q-123",
  "original_price": 5000,
  "winning_price": 4200,
  "competitor": "ABC Woodworks",
  "loss_reason": "Price"
}

# Get pricing insights
GET /api/v1/quotes/lost/insights
```

### Completed Projects

```bash
# Record completed project with actual costs
POST /api/v1/projects/complete
{
  "quote_id": "Q-123",
  "project_name": "Cabinet Project",
  "quoted_price": 5000,
  "quoted_cost": 3000,
  "final_agreed_price": 4500,
  "actual_costs": {
    "material_cost": 1200,
    "labor_cost": 1500,
    "overhead_cost": 500,
    "delivery_cost": 100
  }
}

# Get project insights
GET /api/v1/projects/insights
```

### Configuration

```bash
# Get cost tables
GET /api/v1/config/cost-tables

# Update cost table
PUT /api/v1/config/cost-tables
{
  "table_name": "labor_rates",
  "updates": {"woodwork": 60.00}
}
```

## Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t woodworking-quote-engine .
docker run -p 8000:8000 -v $(pwd)/data:/app/data woodworking-quote-engine
```

## Configuration

### Cost Tables (`config/cost_tables.json`)

The deterministic model uses configurable cost tables:

- `material_costs_per_bf`: Cost per board foot by wood species
- `grade_multipliers`: Multipliers by material grade
- `labor_rates`: Hourly rates by department
- `finishing_costs_per_sqft`: Finishing costs by complexity
- `delivery`: Delivery cost parameters
- `overhead_pct`: Overhead allocation percentage

### Margin Targets

Default margin targets for pricing tiers:
- Value: 25%
- Standard: 40%
- Premium: 55%

## Model Performance

With real historical data, the system provides:
- **Should-Cost Model**: Deterministic baseline from cost components
- **ML Adjustment**: Learns market and estimator patterns
- **Confidence Scoring**: Flags uncertain quotes for review

Note: Model accuracy improves significantly with more historical quote data. The current synthetic data is for testing only.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black src/
isort src/

# Lint
flake8 src/
```

## Roadmap

### Phase 1: Monday.com Integration (Next)
- [ ] Connect to Monday.com API for project management
- [ ] Sync employee hours and availability
- [ ] Build project sprints based on worker expertise
- [ ] Match tasks to employees by skill level
- [ ] Auto-assign resources based on current workload

### Phase 2: Resource Optimization
- [ ] Track employee expertise by task type (woodwork, metal, finishing, etc.)
- [ ] Calculate time-to-value for resource allocation
- [ ] Suggest optimal team assignments for new projects
- [ ] Balance workload across available resources
- [ ] Predict project completion dates based on resource allocation

### Phase 3: Enhanced Features
- [ ] Add more wood species and materials
- [ ] Implement quote versioning and history
- [ ] Add user authentication
- [ ] Create admin dashboard
- [ ] Add batch quote processing
- [ ] Implement quote PDF export
- [ ] Add email notifications
- [ ] Integrate with accounting systems

## License

MIT License - see LICENSE file for details.

## Author

James Adams - Exploring practical ML for small business operations
