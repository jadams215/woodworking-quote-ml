"""JSONL data pack loader for market index ingestion.

Reads JSONL files (one JSON object per line, comment lines starting with #
are skipped) and upserts data into market_index_series and
market_index_observations tables.

Each JSONL record must have a ``dataset`` field that determines how it maps
to the schema.  The loader handles:
  - lumber_price       → series + observation (value_numeric = price_usd_per_bf)
  - labor_benchmark    → series + observation (value_json for percentiles)
  - labor_burden       → series + observation (value_numeric = burden_pct)
  - finish_cost_benchmark → series + observation (value_json for ranges)
  - hardware_price     → series + observation (value_numeric = price_usd)
  - freight_rate       → series + observation (value_numeric = avg_usd_per_mile)
  - fuel_price_index   → series + observation (value_numeric = price_usd_per_gal)
  - construction_demand_signal → series + observation (value_numeric = index)
  - subcontractor_benchmark → series + observation (value_json for ranges)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.market_index import MarketIndexObservation, MarketIndexSeries
from app.utils.decimal_utils import to_decimal


def _parse_date(val: Any) -> date:
    """Parse various date formats to a date object."""
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        # Handle "2026-02-16", "2025-10", "May 2024 (dataset)", etc.
        val = val.strip()
        # Try ISO date first
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                return datetime.strptime(val[:len("2026-02-16" if "-" in val[5:6] else "2026-02")], fmt).date()
            except (ValueError, IndexError):
                continue
        # Extract year-month pattern from longer strings
        import re
        match = re.search(r"(\d{4})-(\d{2})", val)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        # Try "May 2024" etc.
        for fmt in ("%B %Y", "%b %Y"):
            try:
                return datetime.strptime(val[:20].strip().rstrip(" ("), fmt).date()
            except ValueError:
                continue
    return date.today()


def _build_series_key(record: dict) -> tuple[str, str, str]:
    """Extract (dataset, category, name) from a JSONL record."""
    dataset = record.get("dataset", "unknown")
    category = record.get("category", "unknown")

    # Build a unique name based on record type
    if dataset == "lumber_price":
        species = record.get("species", "")
        seller = record.get("seller", "")
        tier = record.get("price_usd_per_bf_tier", "")
        index_name = record.get("index_name", "")
        if species and tier:
            name = f"{species} {tier} ({seller})" if seller else f"{species} {tier}"
        elif species:
            grade = record.get("grade", "")
            region = record.get("region", "")
            name = f"{species} {grade} {region}".strip()
        elif index_name:
            name = index_name
        else:
            name = record.get("source", "unknown")

    elif dataset == "labor_benchmark":
        role = record.get("role", "unknown")
        geo = record.get("geo", "US")
        wage_basis = record.get("wage_basis", "")
        name = f"{role} ({wage_basis}, {geo})"

    elif dataset == "labor_burden":
        industry = record.get("industry", "unknown")
        name = f"Burden rate - {industry}"

    elif dataset == "finish_cost_benchmark":
        process = record.get("process", "unknown")
        basis = record.get("pricing_basis", "")
        name = f"{process} ({basis})"

    elif dataset == "hardware_price":
        item = record.get("item", "unknown")
        sku = record.get("sku", "")
        uom = record.get("uom", "")
        name = f"{item} [{sku}] ({uom})" if sku else item

    elif dataset == "freight_rate":
        equipment = record.get("equipment", "unknown")
        rate_type = record.get("rate_type", "")
        name = f"{equipment} {rate_type}"

    elif dataset == "fuel_price_index":
        series_name = record.get("series", "unknown")
        name = series_name

    elif dataset == "construction_demand_signal":
        metric = record.get("metric", "unknown")
        name = metric

    elif dataset == "subcontractor_benchmark":
        trade = record.get("trade", "unknown")
        basis = record.get("pricing_basis", "")
        name = f"{trade} ({basis})"

    else:
        name = record.get("source", "unknown")

    return (dataset, category, name)


def _extract_unit(record: dict) -> str:
    """Determine the unit of measure from a record."""
    dataset = record.get("dataset", "")
    if "price_usd_per_bf" in record and record.get("price_usd_per_bf") is not None:
        return "usd_per_bf"
    if "price_usd_per_gal" in record:
        return "usd_per_gal"
    if "avg_usd_per_mile" in record:
        return "usd_per_mile"
    if "price_usd" in record:
        return record.get("uom", "each")
    if "dmi_value" in record:
        return "index_value"
    if "wage_usd" in record:
        return "usd_per_year"
    if "burden_pct_of_wages" in record:
        return "pct_of_wages"
    if dataset == "finish_cost_benchmark":
        return "usd_per_sqft"
    if dataset == "subcontractor_benchmark":
        return "usd_per_hr"
    return "unknown"


def _extract_observation_date(record: dict) -> date:
    """Extract the observation date from a record."""
    for field in ("effective_date", "date", "price_period", "effective_period", "period", "week_ending"):
        val = record.get(field)
        if val:
            return _parse_date(val)
    return date.today()


def _extract_numeric_value(record: dict) -> Decimal | None:
    """Extract the primary numeric value from a record."""
    for field in (
        "price_usd_per_bf", "price_usd_per_gal", "avg_usd_per_mile",
        "price_usd", "dmi_value", "wage_usd", "burden_pct_of_wages",
        "usd_per_hr",
    ):
        val = record.get(field)
        if val is not None:
            return to_decimal(val)

    # For range-based data, use midpoint as numeric and store full data in JSON
    low = record.get("low_usd_per_sqft") or record.get("low_usd_per_hr")
    high = record.get("high_usd_per_sqft") or record.get("high_usd_per_hr")
    if low is not None and high is not None:
        return (to_decimal(low) + to_decimal(high)) / Decimal("2")

    return None


def _extract_value_json(record: dict) -> dict | None:
    """Extract structured data for JSON storage."""
    json_fields = {}

    # BLS percentile data
    for field in ("p25_usd_per_hr", "p50_usd_per_hr", "p75_usd_per_hr"):
        if field in record and record[field] is not None:
            json_fields[field] = str(record[field])

    # Range data
    for field in (
        "low_usd_per_sqft", "high_usd_per_sqft",
        "low_usd_per_hr", "high_usd_per_hr",
        "avg_usd_per_item", "range_low_usd_per_item", "range_high_usd_per_item",
        "min_qty", "price_usd_per_bf_tier",
        "mom_change_pct", "yoy_context",
    ):
        if field in record and record[field] is not None:
            json_fields[field] = str(record[field]) if not isinstance(record[field], str) else record[field]

    return json_fields if json_fields else None


def _get_or_create_series(
    db: Session, dataset: str, category: str, name: str, record: dict
) -> MarketIndexSeries:
    """Get existing series or create a new one."""
    existing = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == dataset,
            MarketIndexSeries.category == category,
            MarketIndexSeries.name == name,
        )
        .first()
    )
    if existing:
        return existing

    series = MarketIndexSeries(
        id=uuid4(),
        dataset=dataset,
        category=category,
        name=name,
        unit=_extract_unit(record),
        source_name=record.get("source", "unknown"),
        source_url=record.get("source_url"),
        update_frequency=_infer_frequency(record),
        species=record.get("species"),
        grade=record.get("grade"),
        geo=record.get("geo", "US"),
    )
    db.add(series)
    db.flush()
    return series


def _infer_frequency(record: dict) -> str:
    """Infer update frequency from the dataset type."""
    dataset = record.get("dataset", "")
    freq_map = {
        "fuel_price_index": "weekly",
        "lumber_price": "weekly",
        "freight_rate": "weekly",
        "hardware_price": "weekly",
        "labor_benchmark": "annual",
        "labor_burden": "quarterly",
        "construction_demand_signal": "monthly",
        "finish_cost_benchmark": "quarterly",
        "subcontractor_benchmark": "quarterly",
    }
    return freq_map.get(dataset, "monthly")


def load_jsonl_file(db: Session, file_path: str | Path, ingested_by: str = "jsonl_loader") -> dict:
    """Load a JSONL data pack file into market index tables.

    Skips comment lines (starting with #) and blank lines.
    Returns a summary dict with counts.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {file_path}")

    stats = {
        "lines_read": 0,
        "comments_skipped": 0,
        "records_parsed": 0,
        "series_created": 0,
        "observations_created": 0,
        "observations_skipped": 0,
        "errors": [],
    }

    # Track series created in this run
    known_series: set[tuple[str, str, str]] = set()
    existing_series = {
        (s.dataset, s.category, s.name)
        for s in db.query(MarketIndexSeries).all()
    }

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stats["lines_read"] += 1
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                stats["comments_skipped"] += 1
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                stats["errors"].append(f"Line {line_num}: JSON parse error: {e}")
                continue

            stats["records_parsed"] += 1

            try:
                dataset, category, name = _build_series_key(record)
                series_key = (dataset, category, name)

                # Get or create series
                if series_key not in existing_series and series_key not in known_series:
                    _get_or_create_series(db, dataset, category, name, record)
                    known_series.add(series_key)
                    stats["series_created"] += 1
                elif series_key not in known_series:
                    known_series.add(series_key)

                series = (
                    db.query(MarketIndexSeries)
                    .filter(
                        MarketIndexSeries.dataset == dataset,
                        MarketIndexSeries.category == category,
                        MarketIndexSeries.name == name,
                    )
                    .first()
                )

                if series is None:
                    stats["errors"].append(f"Line {line_num}: Could not find/create series for {series_key}")
                    continue

                # Extract observation data
                obs_date = _extract_observation_date(record)
                value_numeric = _extract_numeric_value(record)
                value_json = _extract_value_json(record)

                if value_numeric is None and value_json is None:
                    stats["errors"].append(f"Line {line_num}: No numeric or JSON value extracted")
                    continue

                # Check for existing observation
                existing_obs = (
                    db.query(MarketIndexObservation)
                    .filter(
                        MarketIndexObservation.series_id == series.id,
                        MarketIndexObservation.observed_date == obs_date,
                    )
                    .first()
                )
                if existing_obs:
                    stats["observations_skipped"] += 1
                    continue

                obs = MarketIndexObservation(
                    id=uuid4(),
                    series_id=series.id,
                    observed_date=obs_date,
                    value_numeric=value_numeric,
                    value_json=value_json,
                    source_url=record.get("source_url"),
                    geo=record.get("geo"),
                    notes=record.get("notes"),
                    ingested_by=ingested_by,
                )
                db.add(obs)
                stats["observations_created"] += 1

            except Exception as e:
                stats["errors"].append(f"Line {line_num}: {type(e).__name__}: {e}")
                continue

    db.flush()
    return stats


def load_jsonl_string(db: Session, content: str, ingested_by: str = "jsonl_loader") -> dict:
    """Load JSONL content from a string (same logic as file loader)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp_path = f.name

    try:
        return load_jsonl_file(db, tmp_path, ingested_by)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
