"""PDF generation for quotes using WeasyPrint and Jinja2."""
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.config import get_settings
from app.models.quote import Quote

settings = get_settings()

# Setup Jinja2 environment
template_dir = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))


def generate_quote_pdf(quote: Quote) -> bytes:
    """
    Generate PDF from quote using HTML template.

    Args:
        quote: Quote ORM instance with all relationships loaded

    Returns:
        PDF as bytes

    Raises:
        Exception: If template rendering or PDF generation fails
    """
    # Load template
    template = jinja_env.get_template("quote.html")

    # Parse cost breakdown from JSON
    breakdown = quote.cost_breakdown or {}
    params = quote.params or {}

    # Prepare template context
    context = {
        # Company info
        "company_name": settings.pdf_company_name,
        "company_address": settings.pdf_company_address,
        "company_phone": settings.pdf_company_phone,
        "company_email": settings.pdf_company_email,
        # Quote metadata
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "date": quote.created_at.strftime("%B %d, %Y"),
        "expires_at": (
            quote.expires_at.strftime("%B %d, %Y") if quote.expires_at else "N/A"
        ),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        # Customer info
        "customer_name": quote.customer.name if quote.customer else "N/A",
        "customer_email": quote.customer.email if quote.customer else None,
        "customer_phone": quote.customer.phone if quote.customer else None,
        # Pricing tiers
        "tier_low_price": f"{quote.tier_low_price:,.2f}",
        "tier_standard_price": f"{quote.tier_standard_price:,.2f}",
        "tier_premium_price": f"{quote.tier_premium_price:,.2f}",
        "selected_tier": quote.selected_tier or "standard",
        # Cost breakdown
        "material_cost": f"{breakdown.get('material_cost', 0):,.2f}",
        "labor_cost": f"{breakdown.get('labor_cost', 0):,.2f}",
        "finishing_cost": breakdown.get("finishing_cost", 0),
        "hardware_cost": breakdown.get("hardware_cost", 0),
        "delivery_cost": breakdown.get("delivery_cost", 0),
        "overhead": f"{breakdown.get('overhead', 0):,.2f}",
        "risk_adjustment": breakdown.get("risk_adjustment", 0),
        "total_cost": f"{quote.total_cost:,.2f}",
        # Quote details
        "material_species": params.get("wood_species", "N/A"),
        "material_grade": params.get("material_grade", "N/A"),
        "quantity": params.get("quantity", 1),
        "confidence_score": quote.confidence_score,
        "risk_flags": quote.risk_flags or [],
        "notes": quote.notes,
    }

    # Render HTML
    html_string = template.render(**context)

    # Generate PDF
    pdf_document = HTML(string=html_string)
    pdf_bytes = pdf_document.write_pdf()

    return pdf_bytes
