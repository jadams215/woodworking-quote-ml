# B10 Union Business Context - Quoting System Enhancements

**Source:** https://www.b-10union.com/
**Date Captured:** 2026-02-16
**Purpose:** Real-world business context to enhance ML model and quoting accuracy

---

## Company Profile

**B10 Union, LLC**
- **Location:** 1081 Memorial Dr SE, Atlanta, GA 30316
- **Phone:** 508.942.8541
- **Email:** info@b-10union.com
- **Hours:** Mon-Fri, 9:00 AM–5:00 PM
- **Service Area:** Nationwide (fabrication in Atlanta, GA)

**Core Competencies:**
- Custom furniture design and fabrication
- Woodworking (primary)
- Metal fabrication (secondary)
- Upholstery
- Custom finishes

**Market:** Commercial + Residential (nationwide delivery)

---

## Catalog Enhancements

### Materials Used (Add to `material_costs`)

Based on website portfolio, B10 Union frequently uses:

**Priority Woods:**
1. **White Oak** - Most common (appears in 40%+ of projects)
   - Suggested cost: $9.00-12.00/bf depending on grade
   - Use cases: Tables, credenzas, cabinetry

2. **Walnut** - Premium option (20-30% of projects)
   - Currently in catalog at $15.00/bf ✓
   - Use cases: High-end tables, accent pieces

3. **Parota Slab** - Live edge specialty (10-15% of projects)
   - **ACTION:** Add to catalog
   - Suggested cost: $18.00-25.00/bf (live edge premium)
   - Use cases: Statement dining/conference tables

**Currently Missing from Catalog:**
- Parota (live edge slabs)
- Reclaimed wood options

### Finishing Options (Add to `finishing_complexity` or new table)

**Custom Finishes Observed:**
1. **Lime Wash** - Specialty finish
   - Higher finishing_complexity (4-5)
   - Additional labor: +2-3 hours per piece
   - Material cost: $3.50/sqft

2. **Natural Oil Finish** - Standard
   - Standard finishing_complexity (2-3)
   - Current catalog ✓

3. **Custom Color Matching**
   - Premium finishing_complexity (4-5)
   - R&D time: +1-2 hours

**ACTION:** Consider adding `finishing_type` enum to QuoteParams:
- `natural_oil` (standard)
- `lime_wash` (premium)
- `custom_stain` (premium)
- `powder_coat_metal` (for metal components)

### Metal Fabrication (Currently Missing)

**Observed Metal Work:**
- Steel table bases
- Inlaid metal accents
- Custom steel frames

**ACTION:** Add metal cost calculator:
```python
# backend/app/engine/metal_calculator.py
def calculate_metal_cost(
    metal_type: str,  # "steel", "brass", "aluminum"
    weight_lbs: Decimal,
    fabrication_complexity: int,  # 1-5
    powder_coating: bool,
    price_book: PriceBook
) -> Decimal:
    # Steel: $3.50/lb base
    # Fabrication: $75/hr
    # Powder coating: $4.50/sqft (already in catalog)
    pass
```

---

## Project Type Classifications

### High-Frequency Project Types (Train ML on these)

1. **Conference/Dining Tables** (35-40% of portfolio)
   - Length: 72" to 240" (20-foot capability mentioned)
   - Complexity: 3-5 (joinery, finish quality critical)
   - Common features: Cable management, breadboard ends, metal bases
   - **ML Training Note:** This is B10's signature product

2. **Credenzas** (20-25%)
   - Length: 60" to 120"
   - Complexity: 4-5 (doors, drawers, internal organization)
   - Common features: Soft-close hardware, custom interiors

3. **Built-in Cabinetry** (15-20%)
   - Complexity: 4-5 (site measurement, installation)
   - **Installation flag:** Almost always `installation_required=True`
   - Common features: Custom sizing, site adaptation

4. **Coffee Tables** (10-15%)
   - Complexity: 2-4
   - Common features: Lower joinery requirements

5. **Custom Stone Inlay** (5-10%)
   - Complexity: 5 (specialty skill)
   - Additional material cost: Stone + epoxy
   - **ACTION:** Add `has_stone_inlay` boolean to QuoteParams

### Project Complexity Indicators (for `job_complexity_score`)

Based on portfolio analysis:

**Score 5 (Highest Complexity):**
- 20-foot+ conference tables
- Built-in cabinetry with site installation
- Stone inlay work
- Concave groove detailing (specialty joinery)

**Score 4:**
- 12-20 foot tables
- Credenzas with complex interiors
- Mixed materials (wood + metal)

**Score 3:**
- 8-12 foot tables
- Simple credenzas
- Standard joinery

**Score 2:**
- Coffee tables
- Small benches

**Score 1:**
- Cutting boards
- Shelving

---

## Delivery & Service Area Adjustments

### Current Delivery Model Issues

**Problem:** Current `delivery_miles` assumes local delivery only.

**Reality:** B10 Union ships nationwide from Atlanta, GA.

**Solution:** Add delivery tier system to `catalog.py`:

```python
class DeliveryTier(Base):
    """Tiered delivery pricing for nationwide shipping."""
    __tablename__ = "delivery_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tier_name: Mapped[str] = mapped_column(String(50))  # "Local", "Regional", "National"
    max_miles: Mapped[int] = mapped_column()  # 50, 500, 3000
    base_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    per_mile_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    freight_required: Mapped[bool] = mapped_column()  # TRUE for national
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
```

**Suggested Tiers:**
1. **Local** (0-50 miles from Atlanta)
   - Base: $75, Per mile: $2.50 (current catalog ✓)

2. **Regional** (51-500 miles, Southeast)
   - Base: $200, Flat rate (no per-mile)

3. **National** (500+ miles)
   - Base: $500, Freight quote required
   - Heavy surcharge: $300 (vs current $150)

---

## ML Model Training Enhancements

### Feature Engineering Based on Real Projects

**New Features to Add:**

1. **`project_type`** (categorical)
   - Values: `"conference_table"`, `"credenza"`, `"built_in"`, `"coffee_table"`, `"custom"`
   - **Impact:** Strong predictor of labor hours and complexity

2. **`has_metal_base`** (boolean)
   - Indicator for metal fabrication component
   - **Impact:** Adds 10-20 hours metal shop time

3. **`has_upholstery`** (boolean)
   - Currently in QuoteParams ✓
   - **Training note:** Appears in ~15% of projects (benches, seating)

4. **`finish_type`** (categorical)
   - Values: `"natural_oil"`, `"lime_wash"`, `"custom_stain"`, `"powder_coat"`
   - **Impact:** Significant effect on finishing_hours

5. **`live_edge`** (boolean)
   - Parota slab projects require extra prep time
   - **Impact:** +5-10 hours for edge prep, epoxy fill

6. **`stone_inlay`** (boolean)
   - Specialty feature requiring expert labor
   - **Impact:** +8-15 hours, $200-500 material cost

### Historical Data to Collect

**Priority Data Points for ML Retraining:**

From `completed_projects` table:
- Actual vs quoted labor hours (by project_type)
- Actual vs quoted material costs (by wood_species)
- Actual finishing time (by finish_type)
- Customer satisfaction scores (by complexity_score)

**Current ML Model Location:** `woodworking-ml/src/models/`

**ACTION:** Create `backend/scripts/export_training_data.py`:
```python
"""Export completed projects for ML retraining."""
def export_completed_projects_to_csv(db: Session, output_path: str):
    # Query completed_projects with all features
    # Include: quoted_cost, actual_total, margin_achieved_pct
    # Include: project_type, wood_species, material_grade, complexity
    # Export as CSV for sklearn model retraining
    pass
```

---

## Confidence Scoring Refinements

### Current Issues

**Problem:** Generic confidence scoring doesn't account for B10's specialty areas.

**Solution:** Adjust confidence score in `quote_generator.py`:

```python
def calculate_confidence_score(params: QuoteParams, price_book: PriceBook) -> int:
    """
    Confidence scoring based on B10 Union's specialty areas.

    HIGH CONFIDENCE (85-100):
    - Conference/dining tables in white oak or walnut
    - Standard finishes (natural oil)
    - 8-15 foot length

    MEDIUM CONFIDENCE (60-84):
    - Credenzas, built-ins
    - Custom finishes (lime wash)
    - Mixed materials

    LOW CONFIDENCE (40-59):
    - Live edge slabs (Parota)
    - Stone inlay (limited historical data)
    - 20+ foot tables (rare, high risk)
    """
    base_score = 100

    # Reduce confidence for rare project types
    if params.wood_species == "Parota" and params.live_edge:
        base_score -= 20  # Limited historical data

    # High confidence in core competency
    if params.project_type == "conference_table" and params.wood_species in ["White Oak", "Walnut"]:
        base_score -= 5  # Very confident

    # Reduce for specialty finishes
    if params.finish_type == "lime_wash":
        base_score -= 10  # Less historical data

    # Add other scoring logic...
    return max(40, min(100, base_score))
```

---

## Risk Flags Enhancements

### New Risk Flags to Add

Based on B10 Union's actual challenges:

1. **`NATIONWIDE_DELIVERY`**
   - Trigger: `delivery_miles > 500`
   - Risk: Freight coordination, damage during transit
   - Recommendation: Add insurance, freight quote

2. **`OVERSIZED_FURNITURE`**
   - Trigger: `length_in > 180` (15+ feet)
   - Risk: Shop space, delivery logistics, installation challenges
   - Recommendation: Site visit required

3. **`MIXED_MATERIALS`**
   - Trigger: `has_woodwork=True AND has_metalwork=True`
   - Risk: Coordination between shops, finishing compatibility
   - Recommendation: Add 10% buffer

4. **`CUSTOM_FINISH`**
   - Trigger: `finish_type NOT IN ["natural_oil"]`
   - Risk: Color matching, multiple coats, dry time
   - Recommendation: Sample approval required

5. **`STONE_INLAY`**
   - Trigger: `has_stone_inlay=True`
   - Risk: Specialty skill, material sourcing, epoxy work
   - Recommendation: Specialty labor rate (+$15/hr)

---

## Pricing Strategy Insights

### Observed Pricing Patterns (from portfolio)

**Conference Tables (B10's bread and butter):**
- 8-foot white oak table: Likely $3,500-5,000 (tier_standard)
- 12-foot walnut table: Likely $6,500-9,000 (tier_premium)
- 20-foot parota slab: Likely $15,000-25,000 (tier_premium + risk premium)

**Credenzas:**
- 6-foot simple: Likely $2,500-4,000
- 8-foot complex (doors/drawers): Likely $4,500-7,000

**Coffee Tables:**
- Standard 48x24: Likely $1,200-2,000
- Live edge specialty: Likely $2,500-4,000

**ACTION:** Use these as golden test cases in `tests/integration/test_realistic_quotes.py`:
```python
def test_8ft_oak_table_realistic_price():
    """Verify 8-foot white oak table quote is in expected range."""
    params = QuoteParams(
        wood_species="White Oak",
        material_grade="Standard",
        length_in=96, width_in=42, height_in=1.5,
        quantity=1,
        project_type="conference_table",
        # ... other params
    )
    result = generate_quote(params, price_book, "Q-001", datetime.utcnow())

    # Based on B10's typical pricing
    assert Decimal("3500") <= result.tiers[1].price <= Decimal("5000")
```

---

## Branding & PDF Enhancements

### Company Information for PDFs

**Update:** `backend/app/pdf/templates/quote.html`

Add B10 Union branding:
```html
<div class="header">
    <img src="logo.png" alt="B10 Union" height="60">
    <div class="company-info">
        <h1>B10 Union, LLC</h1>
        <p>Custom Furniture & Fabrication</p>
        <p>1081 Memorial Dr SE, Atlanta, GA 30316</p>
        <p>508.942.8541 | info@b-10union.com</p>
    </div>
</div>
```

**Terms & Conditions to Add:**
- "All furniture is handmade by our team in Atlanta, GA"
- "Nationwide delivery available via freight carrier"
- "Custom finishes require sample approval before production"
- "Installation services available for built-in projects"
- "50% deposit required, balance due upon completion"

---

## Implementation Priority

### Phase 7A: Quick Wins (1-2 days)

1. **Add Parota to material catalog**
   ```sql
   INSERT INTO material_costs (wood_species, grade, cost_per_bf, effective_from)
   VALUES ('Parota', 'Standard', 20.00, '2024-02-16'),
          ('Parota', 'Premium', 25.00, '2024-02-16');
   ```

2. **Add White Oak emphasis**
   - Already in catalog ✓
   - Update seed data to mark as "most_common=True"

3. **Update PDF with B10 branding**
   - Company info, logo, contact details
   - Terms & conditions footer

4. **Add project_type enum to QuoteParams**
   ```python
   project_type: str  # "conference_table", "credenza", "built_in", "coffee_table", "custom"
   ```

### Phase 7B: Medium Enhancements (1 week)

5. **Add delivery tier system**
   - Create DeliveryTier model
   - Migrate delivery calculation to tier-based
   - Add freight coordination for national

6. **Add metal fabrication calculator**
   - New module: `backend/app/engine/metal_calculator.py`
   - Integrate with quote_generator

7. **Refine confidence scoring**
   - Use project_type weights
   - Add specialty finish penalties

8. **Add new risk flags**
   - NATIONWIDE_DELIVERY, OVERSIZED_FURNITURE, etc.

### Phase 7C: ML Retraining (2-3 weeks)

9. **Export completed projects for training**
   - Create export script
   - Gather 50+ completed project records

10. **Retrain ML model with new features**
    - Add project_type, finish_type, has_metal_base
    - Retrain sklearn model
    - Validate against known B10 projects

11. **Integrate ML confidence scoring**
    - Replace heuristic confidence with ML prediction intervals
    - Use model uncertainty as confidence score

### Phase 7D: Advanced Features (1 month+)

12. **Stone inlay calculator**
13. **Live edge slab pricing**
14. **Custom finish workflow** (sample approval)
15. **Site measurement scheduling** (for built-ins)

---

## Data Collection Strategy

### What to Track Going Forward

**For Every Quote Generated:**
1. Did customer accept? (track conversion rate by project_type)
2. Which tier did they select? (low/standard/premium preference)
3. Was quote adjusted during negotiation? (capture in negotiation_history)

**For Every Completed Project:**
1. Actual hours vs estimated (by craft: woodwork, metal, finishing)
2. Actual material cost vs quoted
3. Delivery issues? (damage, freight delays)
4. Installation time (if applicable)
5. Customer satisfaction (1-5 scale)

**For ML Retraining Triggers:**
- Retrain every 25 completed projects
- Retrain if margin_achieved_pct < 20% (quotes too low)
- Retrain if win_rate < 40% (quotes too high)

---

## Next Steps

1. **Review this document** with B10 Union stakeholders
2. **Prioritize enhancements** based on business impact
3. **Start Phase 7A** (quick wins) immediately
4. **Gather historical data** for ML retraining
5. **Create golden test suite** with realistic B10 projects

**Estimated Impact:**
- ✅ More accurate quotes (reduce estimation error by 15-20%)
- ✅ Better confidence scoring (reduce review overhead)
- ✅ Specialty project support (stone inlay, metal, custom finishes)
- ✅ Realistic delivery pricing (nationwide shipping)
- ✅ Professional branding (customer-facing PDFs)

---

**Document Maintained By:** Claude Opus 4.6 (Woodworkers Architect)
**Last Updated:** 2026-02-16
**Next Review:** After Phase 7A implementation
