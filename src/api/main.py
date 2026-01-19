"""
FastAPI backend for Woodworking Quote Engine.

Provides REST API endpoints for:
- Generating quotes
- Recording lost quotes
- Recording completed projects
- Retrieving insights and analytics
- Managing cost tables
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import json
import os
import base64
import re
import httpx

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models.quote_engine import QuoteEngine, QuoteResult
from src.api.cache import get_cached_quote, cache_quote, invalidate_cache, get_cache_stats


# Pydantic models for request/response
class QuoteRequest(BaseModel):
    """Request model for generating a quote."""
    # Project info
    project_name: Optional[str] = "New Project"
    customer_name: Optional[str] = None

    # Dimensions
    length_in: float = Field(default=0, ge=0, description="Length in inches")
    width_in: float = Field(default=0, ge=0, description="Width in inches")
    height_in: float = Field(default=0, ge=0, description="Height in inches")
    quantity: int = Field(default=1, ge=1, description="Number of units")

    # Materials
    wood_species: str = Field(default="Other", description="Type of wood")
    material_grade: str = Field(default="Standard", description="Material quality grade")

    # Labor
    estimated_labor_hours: float = Field(default=0, ge=0)
    estimated_machine_hours: float = Field(default=0, ge=0)

    # Work types
    has_woodwork: bool = True
    has_metalwork: bool = False
    has_finishing: bool = True
    has_upholstery: bool = False
    has_powder_coating: bool = False

    # Finishing
    finishing_complexity: int = Field(default=3, ge=1, le=5)

    # Costs
    hardware_cost: float = Field(default=0, ge=0)
    finish_material_cost: float = Field(default=0, ge=0)

    # Logistics
    delivery_miles: float = Field(default=0, ge=0)
    installation_required: bool = False

    # Risk
    job_complexity_score: int = Field(default=3, ge=1, le=5)
    risk_adjustment_pct: float = Field(default=0, ge=0, le=25)

    # Notes
    estimator_notes: Optional[str] = None

    # Pricing Intelligence (for model training and adjustments)
    customer_budget: Optional[str] = None  # Budget range category
    competitor_quote: Optional[float] = None  # Known competitor price
    material_type: str = Field(default="solid", description="solid, veneer, mixed, laminate")
    quality_level: str = Field(default="residential", description="commercial, residential, heirloom")
    timeline_urgency: str = Field(default="standard", description="flexible, standard, rush, urgent")
    customer_type: str = Field(default="new", description="new, repeat, referral, commercial")
    pricing_notes: Optional[str] = None  # Free-form pricing context
    scope_clarifications: Optional[str] = None  # Scope details

    # Options
    include_ml_adjustment: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "Custom Maple Cabinet",
                "length_in": 80,
                "width_in": 24,
                "height_in": 36,
                "quantity": 2,
                "wood_species": "Maple",
                "material_grade": "Premium",
                "estimated_labor_hours": 12,
                "finishing_complexity": 4,
                "delivery_miles": 15,
                "installation_required": True,
            }
        }


class LostQuoteRequest(BaseModel):
    """Request model for recording a lost quote."""
    quote_id: str
    original_price: float
    winning_price: float
    competitor: Optional[str] = None
    loss_reason: Optional[str] = None
    notes: str = ""
    parameters: Dict[str, Any] = {}


class NegotiationRequest(BaseModel):
    """Request model for recording a price negotiation."""
    quote_id: str
    adjustment_type: str = Field(..., description="discount, scope_change, material_change, etc.")
    old_price: float
    new_price: float
    reason: str
    notes: str = ""


class CompletedProjectRequest(BaseModel):
    """Request model for recording a completed project."""
    quote_id: str
    project_name: str
    quoted_price: float
    quoted_cost: float
    final_agreed_price: float
    negotiation_rounds: int = 0
    price_adjustments: List[Dict[str, Any]] = []
    actual_costs: Dict[str, float] = Field(
        ...,
        description="Dict with material_cost, labor_cost, overhead_cost, delivery_cost"
    )
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    customer_satisfaction: Optional[int] = Field(default=None, ge=1, le=5)
    issues: Optional[List[str]] = None
    lessons_learned: str = ""


class CostTableUpdate(BaseModel):
    """Request model for updating cost tables."""
    table_name: str
    updates: Dict[str, Any]


class VisionAnalysisRequest(BaseModel):
    """Request model for vision-based furniture analysis."""
    image_data: str = Field(..., description="Base64-encoded image data (data URL format)")


class VisionAnalysisResponse(BaseModel):
    """Response model for vision analysis results."""
    project_type: Optional[str] = None
    wood_species: Optional[str] = None
    material_grade: Optional[str] = None
    estimated_length: Optional[float] = None
    estimated_width: Optional[float] = None
    estimated_height: Optional[float] = None
    finishing_complexity: Optional[int] = None
    job_complexity: Optional[int] = None
    has_metalwork: Optional[bool] = None
    has_upholstery: Optional[bool] = None
    has_finishing: Optional[bool] = None
    description: Optional[str] = None
    overall_confidence: str = "medium"


class ApprovalSubmitRequest(BaseModel):
    """Request model for submitting a quote for manager approval."""
    project_name: str
    customer_budget: Optional[str] = None
    competitor_quote: Optional[float] = None
    material_type: str = "solid"
    quality_level: str = "residential"
    timeline_urgency: str = "standard"
    customer_type: str = "new"
    pricing_notes: Optional[str] = None
    scope_clarifications: Optional[str] = None
    wood_species: Optional[str] = None
    length_in: Optional[float] = None
    width_in: Optional[float] = None
    height_in: Optional[float] = None
    estimated_labor_hours: Optional[float] = None


class ApprovalActionRequest(BaseModel):
    """Request model for manager to approve/reject a quote."""
    status: str = Field(..., description="approved or rejected")
    notes: Optional[str] = None
    message: Optional[str] = None
    suggested_adjustments: Optional[Dict[str, Any]] = None


# In-memory storage for approvals (use database in production)
pending_approvals: Dict[str, Dict[str, Any]] = {}


# Integration request/response models
class IntegrationConfigRequest(BaseModel):
    """Configuration for integration connections."""
    monday_api_key: Optional[str] = None
    quickbooks_access_token: Optional[str] = None
    quickbooks_realm_id: Optional[str] = None
    tsheets_access_token: Optional[str] = None
    gdrive_credentials_path: Optional[str] = None
    gdrive_root_folder_id: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    """Request to create a project from an approved quote."""
    quote_id: str
    customer_name: str
    project_name: str
    quote_result: Dict[str, Any]
    start_date: Optional[str] = None


# Initialize integration clients (lazy loading)
integration_orchestrator = None


def get_orchestrator():
    """Get or create the integration orchestrator."""
    global integration_orchestrator
    if integration_orchestrator is None:
        try:
            from src.integrations.orchestrator import IntegrationOrchestrator
            from src.integrations.monday_client import MondayClient
            from src.integrations.quickbooks_client import QuickBooksClient
            from src.integrations.tsheets_client import TSheetsClient
            from src.integrations.gdrive_client import GoogleDriveClient

            # Initialize clients from environment variables
            monday_client = None
            if os.environ.get('MONDAY_API_KEY'):
                monday_client = MondayClient(api_key=os.environ.get('MONDAY_API_KEY'))

            quickbooks_client = None
            if os.environ.get('QUICKBOOKS_ACCESS_TOKEN'):
                quickbooks_client = QuickBooksClient(
                    access_token=os.environ.get('QUICKBOOKS_ACCESS_TOKEN'),
                    realm_id=os.environ.get('QUICKBOOKS_REALM_ID'),
                    sandbox=os.environ.get('QUICKBOOKS_SANDBOX', 'true').lower() == 'true'
                )

            tsheets_client = None
            if os.environ.get('TSHEETS_ACCESS_TOKEN'):
                tsheets_client = TSheetsClient(access_token=os.environ.get('TSHEETS_ACCESS_TOKEN'))

            gdrive_client = None
            if os.environ.get('GDRIVE_CREDENTIALS_PATH'):
                gdrive_client = GoogleDriveClient(
                    credentials_path=os.environ.get('GDRIVE_CREDENTIALS_PATH'),
                    root_folder_id=os.environ.get('GDRIVE_ROOT_FOLDER_ID')
                )

            integration_orchestrator = IntegrationOrchestrator(
                monday_client=monday_client,
                quickbooks_client=quickbooks_client,
                tsheets_client=tsheets_client,
                gdrive_client=gdrive_client,
            )
        except ImportError as e:
            print(f"Integration modules not available: {e}")
            integration_orchestrator = None

    return integration_orchestrator


# Initialize FastAPI app
app = FastAPI(
    title="Woodworking Quote Engine API",
    description="Real-time quote generation for woodworking projects",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize quote engine
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / 'config' / 'cost_tables.json'
MODEL_DIR = PROJECT_ROOT / 'models'
DATA_DIR = PROJECT_ROOT / 'data'
WEB_DIR = PROJECT_ROOT / 'src' / 'web'

engine: Optional[QuoteEngine] = None

# Serve static files (web UI)
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def get_engine() -> QuoteEngine:
    """Get or initialize the quote engine."""
    global engine
    if engine is None:
        engine = QuoteEngine(
            config_path=CONFIG_PATH if CONFIG_PATH.exists() else None,
            model_dir=MODEL_DIR if MODEL_DIR.exists() else None,
        )
        engine.set_lost_quotes_path(DATA_DIR / 'lost_quotes.json')
        engine.set_completed_projects_path(DATA_DIR / 'completed_projects.json')
    return engine


# Serve the main web UI
@app.get("/")
async def root():
    """Serve the main web UI."""
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Woodworking Quote Engine API", "docs": "/docs"}


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


# Quote generation
@app.post("/api/v1/quotes/generate")
async def generate_quote(
    request: QuoteRequest,
    skip_cache: bool = Query(False, description="Skip cache and force recalculation")
) -> Dict[str, Any]:
    """
    Generate a woodworking quote with all pricing tiers.

    Returns cost breakdown, three pricing tiers (value, standard, premium),
    confidence scores, and risk flags.
    """
    try:
        params = request.model_dump()
        include_ml = params.pop('include_ml_adjustment', True)

        # Extract pricing intelligence fields (don't pass to cost model)
        pricing_intel = {
            'customer_budget': params.pop('customer_budget', None),
            'competitor_quote': params.pop('competitor_quote', None),
            'material_type': params.pop('material_type', 'solid'),
            'quality_level': params.pop('quality_level', 'residential'),
            'timeline_urgency': params.pop('timeline_urgency', 'standard'),
            'customer_type': params.pop('customer_type', 'new'),
            'pricing_notes': params.pop('pricing_notes', None),
            'scope_clarifications': params.pop('scope_clarifications', None),
        }

        # Apply pricing adjustments based on intelligence
        price_multiplier = 1.0
        adjustment_notes = []

        # Material type adjustments
        material_adjustments = {
            'solid': 1.0,       # Base price for solid wood
            'veneer': 0.65,    # Veneer is ~35% cheaper
            'mixed': 0.80,     # Mixed is ~20% cheaper
            'laminate': 0.45,  # Laminate is ~55% cheaper
        }
        mat_mult = material_adjustments.get(pricing_intel['material_type'], 1.0)
        if mat_mult != 1.0:
            price_multiplier *= mat_mult
            adjustment_notes.append(f"Material type ({pricing_intel['material_type']}): {(mat_mult-1)*100:+.0f}%")

        # Quality level adjustments
        quality_adjustments = {
            'commercial': 0.85,   # Commercial grade is simpler
            'residential': 1.0,   # Base
            'heirloom': 1.35,     # Premium craftsmanship
        }
        qual_mult = quality_adjustments.get(pricing_intel['quality_level'], 1.0)
        if qual_mult != 1.0:
            price_multiplier *= qual_mult
            adjustment_notes.append(f"Quality level ({pricing_intel['quality_level']}): {(qual_mult-1)*100:+.0f}%")

        # Timeline urgency adjustments
        timeline_adjustments = {
            'flexible': 0.95,   # Discount for flexibility
            'standard': 1.0,    # Base
            'rush': 1.15,       # 15% rush fee
            'urgent': 1.30,     # 30% urgent fee
        }
        time_mult = timeline_adjustments.get(pricing_intel['timeline_urgency'], 1.0)
        if time_mult != 1.0:
            price_multiplier *= time_mult
            adjustment_notes.append(f"Timeline ({pricing_intel['timeline_urgency']}): {(time_mult-1)*100:+.0f}%")

        # Customer type adjustments
        customer_adjustments = {
            'new': 1.0,         # Base
            'repeat': 0.95,     # 5% loyalty discount
            'referral': 0.97,   # 3% referral discount
            'commercial': 0.92, # 8% volume discount
        }
        cust_mult = customer_adjustments.get(pricing_intel['customer_type'], 1.0)
        if cust_mult != 1.0:
            price_multiplier *= cust_mult
            adjustment_notes.append(f"Customer type ({pricing_intel['customer_type']}): {(cust_mult-1)*100:+.0f}%")

        # Check cache first (unless skipped)
        if not skip_cache:
            cached = get_cached_quote(params)
            if cached:
                cached['from_cache'] = True
                return cached

        eng = get_engine()
        result = eng.generate_quote(params, include_ml=include_ml)
        result_dict = result.to_dict()

        # Apply pricing adjustments to tiers
        if price_multiplier != 1.0:
            for tier_name in ['low', 'standard', 'premium']:
                if tier_name in result_dict.get('tiers', {}):
                    original = result_dict['tiers'][tier_name]['price']
                    adjusted = original * price_multiplier
                    result_dict['tiers'][tier_name]['price'] = round(adjusted, 2)
                    result_dict['tiers'][tier_name]['original_price'] = original

            # Add adjustment info to result
            result_dict['pricing_adjustments'] = {
                'multiplier': round(price_multiplier, 3),
                'adjustments': adjustment_notes,
            }

        # Add competitor context if provided
        if pricing_intel['competitor_quote']:
            comp_quote = pricing_intel['competitor_quote']
            std_price = result_dict.get('tiers', {}).get('standard', {}).get('price', 0)
            if std_price > 0:
                diff_pct = ((std_price - comp_quote) / comp_quote) * 100
                result_dict['competitor_analysis'] = {
                    'competitor_quote': comp_quote,
                    'our_standard_price': std_price,
                    'difference_pct': round(diff_pct, 1),
                    'recommendation': 'Price is competitive' if diff_pct < 10 else
                                     'Consider value tier' if diff_pct > 20 else
                                     'Slightly above competitor'
                }

        # Store pricing intel for future model training
        result_dict['pricing_intelligence'] = pricing_intel

        # Cache the result
        cache_quote(params, result_dict)
        result_dict['from_cache'] = False

        return result_dict

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/quotes/{quote_id}")
async def get_quote(quote_id: str):
    """Get a previously generated quote by ID."""
    # In production, this would retrieve from a database
    raise HTTPException(status_code=501, detail="Quote storage not implemented yet")


# Lost quotes
@app.post("/api/v1/quotes/lost")
async def record_lost_quote(request: LostQuoteRequest) -> Dict[str, Any]:
    """
    Record a quote that was lost to competition.

    This data is used to improve future pricing recommendations.
    """
    try:
        eng = get_engine()

        lost = eng.record_lost_quote(
            quote_id=request.quote_id,
            original_price=request.original_price,
            winning_price=request.winning_price,
            parameters=request.parameters,
            competitor=request.competitor,
            loss_reason=request.loss_reason,
            notes=request.notes,
        )

        return {
            "success": True,
            "quote_id": lost.quote_id,
            "difference_pct": lost.difference_pct,
            "message": f"Lost quote recorded. You were {lost.difference_pct:.1f}% above the winning price."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/quotes/lost/insights")
async def get_lost_quote_insights() -> Dict[str, Any]:
    """
    Get insights from lost quote history.

    Returns analysis of pricing patterns and recommendations.
    """
    try:
        eng = get_engine()
        return eng.get_lost_quote_insights()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Negotiations
@app.post("/api/v1/negotiations")
async def record_negotiation(request: NegotiationRequest) -> Dict[str, Any]:
    """
    Record a price adjustment during customer negotiation.

    Track price changes as the quote evolves through discussions.
    """
    try:
        eng = get_engine()

        adjustment = eng.record_negotiation(
            quote_id=request.quote_id,
            adjustment_type=request.adjustment_type,
            old_price=request.old_price,
            new_price=request.new_price,
            reason=request.reason,
            notes=request.notes,
        )

        return {
            "success": True,
            "adjustment": adjustment,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Completed projects
@app.post("/api/v1/projects/complete")
async def complete_project(request: CompletedProjectRequest) -> Dict[str, Any]:
    """
    Record a completed project with actual costs.

    Compare quoted vs actual to improve future estimates.
    """
    try:
        eng = get_engine()

        project = eng.complete_project(
            quote_id=request.quote_id,
            project_name=request.project_name,
            quoted_price=request.quoted_price,
            quoted_cost=request.quoted_cost,
            final_agreed_price=request.final_agreed_price,
            negotiation_rounds=request.negotiation_rounds,
            price_adjustments=request.price_adjustments,
            actual_costs=request.actual_costs,
            parameters=request.parameters,
            start_date=request.start_date,
            end_date=request.end_date,
            customer_satisfaction=request.customer_satisfaction,
            issues=request.issues,
            lessons_learned=request.lessons_learned,
        )

        return {
            "success": True,
            "project_id": project.quote_id,
            "cost_variance_pct": project.cost_variance_pct,
            "margin_achieved_pct": project.margin_achieved_pct,
            "message": f"Project recorded. Cost variance: {project.cost_variance_pct:+.1f}%, Margin achieved: {project.margin_achieved_pct:.1f}%"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/projects/insights")
async def get_project_insights() -> Dict[str, Any]:
    """
    Get insights from completed project history.

    Returns analysis of cost accuracy and margin performance.
    """
    try:
        eng = get_engine()
        return eng.get_project_insights()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Cost tables management
@app.get("/api/v1/config/cost-tables")
async def get_cost_tables() -> Dict[str, Any]:
    """Get current cost tables configuration."""
    try:
        eng = get_engine()
        return eng.should_cost_model.cost_tables
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/config/cost-tables")
async def update_cost_table(update: CostTableUpdate) -> Dict[str, Any]:
    """
    Update a specific cost table.

    Example: Update material costs, labor rates, etc.
    """
    try:
        eng = get_engine()

        if update.table_name not in eng.should_cost_model.cost_tables:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown cost table: {update.table_name}"
            )

        # Update the table
        if isinstance(eng.should_cost_model.cost_tables[update.table_name], dict):
            eng.should_cost_model.cost_tables[update.table_name].update(update.updates)
        else:
            eng.should_cost_model.cost_tables[update.table_name] = update.updates

        # Save updated config
        eng.should_cost_model.save_config(CONFIG_PATH)

        return {
            "success": True,
            "message": f"Cost table '{update.table_name}' updated",
            "updated_table": eng.should_cost_model.cost_tables[update.table_name],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Options/dropdowns
@app.get("/api/v1/options/wood-species")
async def get_wood_species():
    """Get available wood species options."""
    return {
        "options": [
            {"value": "Pine", "label": "Pine", "price_tier": "low"},
            {"value": "MDF", "label": "MDF", "price_tier": "low"},
            {"value": "Plywood", "label": "Plywood", "price_tier": "low"},
            {"value": "Oak", "label": "Oak", "price_tier": "medium"},
            {"value": "Maple", "label": "Maple", "price_tier": "medium"},
            {"value": "Cherry", "label": "Cherry", "price_tier": "high"},
            {"value": "Walnut", "label": "Walnut", "price_tier": "high"},
            {"value": "Other", "label": "Other/Custom", "price_tier": "medium"},
        ]
    }


@app.get("/api/v1/options/material-grades")
async def get_material_grades():
    """Get available material grade options."""
    return {
        "options": [
            {"value": "Economy", "label": "Economy", "description": "Budget-friendly option"},
            {"value": "Standard", "label": "Standard", "description": "Recommended for most projects"},
            {"value": "Premium", "label": "Premium", "description": "Highest quality materials"},
        ]
    }


@app.get("/api/v1/options/complexity-levels")
async def get_complexity_levels():
    """Get job complexity level options."""
    return {
        "options": [
            {"value": 1, "label": "Very Simple", "description": "Basic, straightforward work"},
            {"value": 2, "label": "Simple", "description": "Standard complexity"},
            {"value": 3, "label": "Moderate", "description": "Average project complexity"},
            {"value": 4, "label": "Complex", "description": "Custom work, multiple techniques"},
            {"value": 5, "label": "Very Complex", "description": "Highly specialized, intricate work"},
        ]
    }


@app.get("/api/v1/options/risk-levels")
async def get_risk_levels():
    """Get project risk level options with explanations."""
    return {
        "options": [
            {
                "value": 0,
                "label": "Standard",
                "description": "Familiar work, reliable materials, known customer",
                "buffer_pct": 0
            },
            {
                "value": 5,
                "label": "Low Risk",
                "description": "Minor unknowns, standard deadline",
                "buffer_pct": 5
            },
            {
                "value": 10,
                "label": "Medium Risk",
                "description": "New design, tight timeline, or material availability concerns",
                "buffer_pct": 10
            },
            {
                "value": 15,
                "label": "High Risk",
                "description": "Complex specs, new customer, or rush job",
                "buffer_pct": 15
            },
            {
                "value": 20,
                "label": "Very High Risk",
                "description": "Multiple uncertainties - unfamiliar work, tight deadline, and complex specs",
                "buffer_pct": 20
            },
        ]
    }


@app.get("/api/v1/quotes/similar")
async def get_similar_projects(
    length: Optional[float] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    species: Optional[str] = None,
    limit: int = Query(6, ge=1, le=20)
) -> List[Dict[str, Any]]:
    """
    Get similar historical projects for reference.

    Can filter by dimensions or wood species. Returns projects
    with pricing that can be used as starting points.
    """
    try:
        eng = get_engine()

        # Get completed projects
        projects = eng.completed_projects

        # If we have real completed projects, use those
        if projects:
            similar = []
            for p in projects:
                params = p.parameters
                similar.append({
                    "name": p.project_name,
                    "dims": f"{params.get('length_in', 0)}x{params.get('width_in', 0)}x{params.get('height_in', 0)}",
                    "species": params.get('wood_species', 'Unknown'),
                    "price": p.final_agreed_price,
                    "completed": p.completion_date,
                })
            return similar[:limit]

        # Fallback: return sample projects for demonstration
        sample_projects = [
            {"name": "Executive Desk", "dims": "72x36x30", "species": "Walnut", "price": 4500},
            {"name": "Kitchen Cabinet Set", "dims": "120x24x36", "species": "Maple", "price": 8200},
            {"name": "Dining Table", "dims": "84x42x30", "species": "Oak", "price": 3800},
            {"name": "Bookshelf Unit", "dims": "48x12x72", "species": "Cherry", "price": 2400},
            {"name": "TV Console", "dims": "60x18x24", "species": "Walnut", "price": 2100},
            {"name": "Custom Credenza", "dims": "66x20x32", "species": "Maple", "price": 3200},
            {"name": "Office Reception Desk", "dims": "96x30x42", "species": "Oak", "price": 5800},
            {"name": "Bathroom Vanity", "dims": "48x22x34", "species": "Cherry", "price": 2800},
        ]

        # Filter by species if provided
        if species:
            sample_projects = [p for p in sample_projects if p['species'].lower() == species.lower()]

        return sample_projects[:limit]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Cache management
@app.get("/api/v1/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    return get_cache_stats()


@app.post("/api/v1/cache/clear")
async def clear_cache():
    """Clear all cached quotes."""
    count = invalidate_cache()
    return {"success": True, "cleared_entries": count}


# Approval workflow endpoints
@app.post("/api/v1/approvals/submit")
async def submit_for_approval(request: ApprovalSubmitRequest) -> Dict[str, Any]:
    """
    Submit a quote for manager approval.

    Creates an approval request that managers can review.
    """
    import uuid

    approval_id = str(uuid.uuid4())[:8]

    approval = {
        "approval_id": approval_id,
        "status": "pending",
        "submitted_at": datetime.now().isoformat(),
        "quote_data": request.model_dump(),
        "notes": None,
        "message": None,
        "suggested_adjustments": None,
        "reviewed_at": None,
        "reviewed_by": None,
    }

    pending_approvals[approval_id] = approval

    return {
        "success": True,
        "approval_id": approval_id,
        "status": "pending",
        "message": "Quote submitted for manager approval",
    }


@app.get("/api/v1/approvals/{approval_id}")
async def get_approval_status(approval_id: str) -> Dict[str, Any]:
    """
    Get the status of an approval request.

    Used for polling to check if a manager has responded.
    """
    if approval_id not in pending_approvals:
        raise HTTPException(status_code=404, detail="Approval request not found")

    approval = pending_approvals[approval_id]

    return {
        "approval_id": approval_id,
        "status": approval["status"],
        "submitted_at": approval["submitted_at"],
        "reviewed_at": approval.get("reviewed_at"),
        "reviewed_by": approval.get("reviewed_by"),
        "notes": approval.get("notes"),
        "message": approval.get("message"),
        "suggested_adjustments": approval.get("suggested_adjustments"),
    }


@app.get("/api/v1/approvals")
async def list_pending_approvals() -> Dict[str, Any]:
    """
    List all pending approval requests (for manager dashboard).
    """
    pending = [
        {
            "approval_id": aid,
            "project_name": data["quote_data"].get("project_name", "Unknown"),
            "submitted_at": data["submitted_at"],
            "status": data["status"],
            "quote_data": data["quote_data"],
        }
        for aid, data in pending_approvals.items()
        if data["status"] == "pending"
    ]

    return {
        "pending_count": len(pending),
        "approvals": pending,
    }


@app.post("/api/v1/approvals/{approval_id}/action")
async def process_approval(approval_id: str, request: ApprovalActionRequest) -> Dict[str, Any]:
    """
    Manager action on an approval request (approve or reject).

    Includes optional notes and suggested adjustments.
    """
    if approval_id not in pending_approvals:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if request.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    approval = pending_approvals[approval_id]
    approval["status"] = request.status
    approval["notes"] = request.notes
    approval["message"] = request.message
    approval["suggested_adjustments"] = request.suggested_adjustments
    approval["reviewed_at"] = datetime.now().isoformat()
    approval["reviewed_by"] = "Manager"  # Would use actual user in production

    return {
        "success": True,
        "approval_id": approval_id,
        "status": request.status,
        "message": f"Quote {request.status}",
    }


@app.post("/api/v1/approvals/{approval_id}/cancel")
async def cancel_approval(approval_id: str) -> Dict[str, Any]:
    """
    Cancel a pending approval request.
    """
    if approval_id in pending_approvals:
        del pending_approvals[approval_id]

    return {
        "success": True,
        "message": "Approval request cancelled",
    }


# Vision Analysis endpoint
@app.post("/api/v1/vision/analyze", response_model=VisionAnalysisResponse)
async def analyze_furniture_image(request: VisionAnalysisRequest) -> Dict[str, Any]:
    """
    Analyze a furniture image using Claude Vision to extract project details.

    Takes a base64-encoded image and returns structured furniture analysis
    including project type, wood species, dimensions, and complexity estimates.
    """
    try:
        # Get API key from environment
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY environment variable not set. Please set it to use vision analysis."
            )

        # Parse the image data (handle data URL format)
        image_data = request.image_data
        if image_data.startswith('data:'):
            # Extract the base64 part from data URL
            match = re.match(r'data:image/(\w+);base64,(.+)', image_data)
            if match:
                media_type = f"image/{match.group(1)}"
                base64_data = match.group(2)
            else:
                raise HTTPException(status_code=400, detail="Invalid image data format")
        else:
            # Assume raw base64, default to jpeg
            media_type = "image/jpeg"
            base64_data = image_data

        # Build the prompt for furniture analysis
        analysis_prompt = """Analyze this image of furniture or woodworking project. Extract the following information and respond in JSON format only (no markdown, no explanation):

{
  "project_type": "The type of furniture (e.g., 'Conference Table', 'Executive Desk', 'Kitchen Cabinet', 'Bookshelf', 'Dining Table', 'Dresser', 'Bed Frame', etc.)",
  "wood_species": "Estimated wood type (e.g., 'Walnut', 'Oak', 'Maple', 'Cherry', 'Pine', 'MDF', 'Plywood', or 'Unknown')",
  "material_grade": "Quality level: 'Economy', 'Standard', or 'Premium'",
  "estimated_length": "Estimated length in inches (number only, use common furniture dimensions as reference)",
  "estimated_width": "Estimated width in inches (number only)",
  "estimated_height": "Estimated height in inches (number only)",
  "finishing_complexity": "1-5 scale (1=raw/minimal, 2=basic stain, 3=moderate finish, 4=complex multi-step, 5=elaborate/artistic)",
  "job_complexity": "1-5 scale (1=very simple, 2=simple, 3=moderate, 4=complex, 5=very complex/intricate)",
  "has_metalwork": "true/false - does it have metal components (legs, handles, brackets)?",
  "has_upholstery": "true/false - does it have fabric, leather, or cushioning?",
  "has_finishing": "true/false - does it appear to have stain, lacquer, or paint finish?",
  "description": "Brief 1-2 sentence description of what you see",
  "overall_confidence": "low/medium/high - how confident are you in this analysis?"
}

Important notes:
- For dimensions, estimate based on typical furniture sizes and any visible reference points
- A standard desk is typically 60-72" long, 24-36" wide, 28-30" high
- A dining table is typically 72-96" long, 36-42" wide, 28-30" high
- Kitchen base cabinets are typically 24" deep, 34.5" high
- Be conservative with complexity scores unless clear evidence of intricate work
- Return ONLY the JSON object, no additional text"""

        # Call Claude API with vision
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": base64_data,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": analysis_prompt,
                                }
                            ],
                        }
                    ],
                },
            )

            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Claude API error: {error_detail}"
                )

            result = response.json()

            # Extract the text content from Claude's response
            if 'content' not in result or len(result['content']) == 0:
                raise HTTPException(status_code=500, detail="Empty response from Claude API")

            text_content = result['content'][0].get('text', '')

            # Parse the JSON response
            try:
                # Try to extract JSON from the response (in case there's any extra text)
                json_match = re.search(r'\{[\s\S]*\}', text_content)
                if json_match:
                    analysis = json.loads(json_match.group())
                else:
                    raise ValueError("No JSON found in response")
            except json.JSONDecodeError as e:
                # If JSON parsing fails, return a basic response
                return {
                    "project_type": "Custom Furniture",
                    "description": text_content[:200] if text_content else "Unable to analyze image",
                    "overall_confidence": "low"
                }

            # Convert string booleans to actual booleans
            for field in ['has_metalwork', 'has_upholstery', 'has_finishing']:
                if field in analysis:
                    if isinstance(analysis[field], str):
                        analysis[field] = analysis[field].lower() == 'true'

            # Convert string numbers to floats/ints
            for field in ['estimated_length', 'estimated_width', 'estimated_height']:
                if field in analysis and analysis[field] is not None:
                    try:
                        analysis[field] = float(analysis[field])
                    except (ValueError, TypeError):
                        analysis[field] = None

            for field in ['finishing_complexity', 'job_complexity']:
                if field in analysis and analysis[field] is not None:
                    try:
                        analysis[field] = int(analysis[field])
                    except (ValueError, TypeError):
                        analysis[field] = 3  # Default to moderate

            return analysis

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")


# ===== Integration Endpoints =====

@app.get("/api/v1/integrations/status")
async def get_integration_status() -> Dict[str, Any]:
    """
    Get connection status for all integrations.

    Returns status for Monday.com, QuickBooks, TSheets, and Google Drive.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        return {
            "available": False,
            "message": "Integration modules not installed",
            "integrations": {
                "monday": {"name": "Monday.com", "connected": False, "error": "Not configured"},
                "quickbooks": {"name": "QuickBooks", "connected": False, "error": "Not configured"},
                "tsheets": {"name": "TSheets (QuickBooks Time)", "connected": False, "error": "Not configured"},
                "gdrive": {"name": "Google Drive", "connected": False, "error": "Not configured"},
            }
        }

    try:
        status = orchestrator.get_integration_status()
        return {
            "available": True,
            "integrations": {
                name: {
                    "name": s.name,
                    "connected": s.connected,
                    "last_sync": s.last_sync,
                    "error": s.error,
                    "details": s.details,
                }
                for name, s in status.items()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/integrations/project/create")
async def create_project_from_quote(request: ProjectCreateRequest) -> Dict[str, Any]:
    """
    Create a project across all integrated systems from an approved quote.

    This will:
    1. Create a Monday.com board with tasks
    2. Create a QuickBooks estimate
    3. Create a Google Drive folder structure
    4. Set up TSheets job codes for time tracking
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Integration modules not available"
        )

    try:
        result = orchestrator.create_project_from_quote(
            quote_id=request.quote_id,
            quote_result=request.quote_result,
            customer_name=request.customer_name,
            start_date=request.start_date
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations/project/{quote_id}/summary")
async def get_project_summary(quote_id: str) -> Dict[str, Any]:
    """
    Get unified project summary from all integrated systems.

    Combines data from Monday.com, QuickBooks, TSheets, and Google Drive.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Integration modules not available"
        )

    try:
        summary = orchestrator.get_project_summary(quote_id)
        return {
            "project_id": summary.project_id,
            "project_name": summary.project_name,
            "customer": summary.customer,
            "status": summary.status,
            "quote": {
                "quoted_price": summary.quoted_price,
                "quote_date": summary.quote_date,
            },
            "monday": {
                "board_id": summary.monday_board_id,
                "tasks_total": summary.tasks_total,
                "tasks_completed": summary.tasks_completed,
                "current_sprint": summary.current_sprint,
                "assigned_workers": summary.assigned_workers,
            },
            "financials": {
                "invoiced_amount": summary.invoiced_amount,
                "payments_received": summary.payments_received,
                "expenses_recorded": summary.expenses_recorded,
                "current_margin_pct": summary.current_margin_pct,
            },
            "labor": {
                "estimated_hours": summary.labor_hours_estimated,
                "actual_hours": summary.labor_hours_actual,
                "variance_pct": summary.labor_variance_pct,
            },
            "documents": {
                "drive_folder_url": summary.drive_folder_url,
                "document_count": summary.document_count,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations/project/{quote_id}/alerts")
async def get_project_alerts(quote_id: str) -> Dict[str, Any]:
    """
    Get alerts/warnings for a project across all systems.

    Checks for budget overruns, labor variance, overdue tasks, etc.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        return {"alerts": [], "message": "Integrations not available"}

    try:
        alerts = orchestrator.get_project_alerts(quote_id)
        return {
            "quote_id": quote_id,
            "alert_count": len(alerts),
            "alerts": alerts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations/team/utilization")
async def get_team_utilization() -> Dict[str, Any]:
    """
    Get current team utilization across all projects.

    Shows worker availability and current workload.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        return {"workers": [], "message": "Integrations not available"}

    try:
        utilization = orchestrator.get_team_utilization()
        return {
            "team_size": len(utilization),
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "name": w.worker_name,
                    "current_hours_weekly": w.current_hours_weekly,
                    "available_hours_weekly": w.available_hours_weekly,
                    "utilization_pct": w.utilization_pct,
                    "assigned_projects": w.assigned_projects,
                    "primary_skills": w.primary_skills,
                }
                for w in utilization
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations/dashboard")
async def get_integrations_dashboard() -> Dict[str, Any]:
    """
    Get unified dashboard data from all integrated systems.

    Returns summary metrics for projects, financials, labor, and alerts.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        return {
            "available": False,
            "message": "Integration modules not available",
        }

    try:
        dashboard = orchestrator.get_dashboard_data()
        return {
            "available": True,
            **dashboard,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/integrations/project/{quote_id}/sync-labor")
async def sync_labor_to_financials(quote_id: str) -> Dict[str, Any]:
    """
    Sync labor hours from TSheets to QuickBooks.

    Updates project expenses based on actual time tracked.
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Integration modules not available"
        )

    try:
        result = orchestrator.sync_labor_to_financials(quote_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/integrations/project/{quote_id}/complete")
async def complete_project(
    quote_id: str,
    customer_satisfaction: Optional[int] = None,
    lessons_learned: str = ""
) -> Dict[str, Any]:
    """
    Mark a project as complete and archive across all systems.

    Actions:
    - Mark complete in Monday.com
    - Generate final invoice in QuickBooks
    - Archive documents in Google Drive
    - Record completed project data
    """
    orchestrator = get_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Integration modules not available"
        )

    try:
        result = orchestrator.complete_project(
            quote_id=quote_id,
            customer_satisfaction=customer_satisfaction,
            lessons_learned=lessons_learned
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run server
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
