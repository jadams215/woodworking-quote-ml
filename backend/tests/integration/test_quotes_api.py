"""Integration tests for quotes API."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.customer import Customer
from app.models.quote import QuoteStatus
from app.models.user import User, UserRole


def test_full_quote_flow(client, db):
    """Test complete quote creation flow: login -> create customer -> create quote -> get quote."""
    # Create admin user
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",  # "password"
        full_name="Admin User",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()

    # Login
    response = client.post(
        "/api/v2/auth/login",
        data={"username": "admin@test.com", "password": "password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create customer
    response = client.post(
        "/api/v2/customers",
        json={
            "name": "Test Customer",
            "email": "customer@test.com",
            "phone": "555-1234",
        },
        headers=headers,
    )
    assert response.status_code == 201
    customer_id = response.json()["id"]

    # Create quote
    quote_data = {
        "customer_id": customer_id,
        "wood_species": "Oak",
        "material_grade": "Standard",
        "length_in": 48.0,
        "width_in": 24.0,
        "height_in": 2.0,
        "quantity": 1,
        "estimated_labor_hours": 10.0,
        "estimated_machine_hours": 0.0,
        "has_woodwork": True,
        "has_metalwork": False,
        "has_finishing": False,
        "has_upholstery": False,
        "finishing_complexity": 2,
        "hardware_cost": 50.0,
        "job_complexity_score": 3,
        "risk_adjustment_pct": 0.0,
    }

    response = client.post("/api/v2/quotes", json=quote_data, headers=headers)
    assert response.status_code == 201
    quote = response.json()

    # Verify quote structure
    assert "id" in quote
    assert "quote_number" in quote
    assert quote["customer_id"] == customer_id
    assert quote["status"] == "draft"
    assert "tier_low_price" in quote
    assert "tier_standard_price" in quote
    assert "tier_premium_price" in quote
    assert "confidence_score" in quote

    # Verify all prices are valid decimals (stored as strings in JSON)
    tier_low = Decimal(str(quote["tier_low_price"]))
    tier_standard = Decimal(str(quote["tier_standard_price"]))
    tier_premium = Decimal(str(quote["tier_premium_price"]))

    # Premium should be highest
    assert tier_premium > tier_standard > tier_low

    # Get quote by ID
    quote_id = quote["id"]
    response = client.get(f"/api/v2/quotes/{quote_id}", headers=headers)
    assert response.status_code == 200
    retrieved_quote = response.json()
    assert retrieved_quote["id"] == quote_id


def test_quote_reproducibility(client, db):
    """Test that quotes can be reproduced from snapshots."""
    # Setup: create admin and customer
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
        full_name="Admin User",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)

    customer = Customer(name="Test Customer", email="test@test.com")
    db.add(customer)
    db.commit()

    # Login
    response = client.post(
        "/api/v2/auth/login",
        data={"username": "admin@test.com", "password": "password"},
    )
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create quote
    quote_data = {
        "customer_id": str(customer.id),
        "wood_species": "Oak",
        "material_grade": "Standard",
        "length_in": 36.0,
        "width_in": 18.0,
        "height_in": 1.5,
        "quantity": 2,
        "estimated_labor_hours": 8.0,
        "estimated_machine_hours": 0.0,
        "has_woodwork": True,
        "has_metalwork": False,
        "has_finishing": False,
        "has_upholstery": False,
        "finishing_complexity": 2,
        "hardware_cost": 0.0,
        "job_complexity_score": 3,
        "risk_adjustment_pct": 0.0,
    }

    response = client.post("/api/v2/quotes", json=quote_data, headers=headers)
    quote = response.json()
    quote_id = quote["id"]
    original_cost = quote["total_cost"]

    # Reproduce quote
    response = client.post(f"/api/v2/quotes/{quote_id}/reproduce", headers=headers)
    assert response.status_code == 200
    reproduction = response.json()

    # Should match exactly
    assert reproduction["matches"] is True
    assert reproduction["reproduced_cost"] == original_cost


def test_quote_requires_authentication(client):
    """Test that quote endpoints require authentication."""
    # Try to create quote without auth
    response = client.post("/api/v2/quotes", json={})
    assert response.status_code == 401

    # Try to list quotes without auth
    response = client.get("/api/v2/quotes")
    assert response.status_code == 401


def test_quote_list_filtering(client, db):
    """Test quote list filtering by customer and status."""
    # Setup
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
        full_name="Admin User",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)

    customer1 = Customer(name="Customer 1")
    customer2 = Customer(name="Customer 2")
    db.add_all([customer1, customer2])
    db.commit()

    # Login
    response = client.post(
        "/api/v2/auth/login",
        data={"username": "admin@test.com", "password": "password"},
    )
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create quotes for customer 1
    for i in range(2):
        quote_data = {
            "customer_id": str(customer1.id),
            "wood_species": "Pine",
            "material_grade": "Standard",
            "length_in": 24.0,
            "width_in": 12.0,
            "height_in": 1.0,
            "quantity": 1,
            "estimated_labor_hours": 5.0,
            "estimated_machine_hours": 0.0,
            "has_woodwork": True,
            "has_metalwork": False,
            "has_finishing": False,
            "has_upholstery": False,
            "finishing_complexity": 2,
            "hardware_cost": 0.0,
            "job_complexity_score": 3,
            "risk_adjustment_pct": 0.0,
        }
        client.post("/api/v2/quotes", json=quote_data, headers=headers)

    # Filter by customer
    response = client.get(
        f"/api/v2/quotes?customer_id={customer1.id}",
        headers=headers,
    )
    assert response.status_code == 200
    quotes = response.json()
    assert len(quotes) == 2
    assert all(q["customer_id"] == str(customer1.id) for q in quotes)

    # Filter by status
    response = client.get(
        "/api/v2/quotes?status=draft",
        headers=headers,
    )
    assert response.status_code == 200
    quotes = response.json()
    assert all(q["status"] == "draft" for q in quotes)
