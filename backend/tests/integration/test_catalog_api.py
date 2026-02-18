"""Integration tests for catalog API."""
from datetime import date

import pytest

from app.models.catalog import MaterialCost
from app.models.user import User, UserRole


def test_get_active_materials(client, db):
    """Test retrieving active material costs."""
    # Setup: create admin user and material costs
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
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
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get materials
    response = client.get("/api/v2/catalog/materials", headers=headers)
    assert response.status_code == 200
    materials = response.json()

    # Should have materials from seed data
    assert len(materials) > 0
    assert all("wood_species" in m for m in materials)
    assert all("grade" in m for m in materials)
    assert all("cost_per_bf" in m for m in materials)


def test_update_material_cost_creates_new_effective_row(client, db):
    """Test that updating material cost creates new effective-dated row."""
    # Setup
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
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
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get current Oak/Standard cost
    response = client.get("/api/v2/catalog/materials", headers=headers)
    materials = response.json()
    oak_standard = next(
        (m for m in materials if m["wood_species"] == "Oak" and m["grade"] == "Standard"),
        None,
    )
    assert oak_standard is not None
    old_cost = oak_standard["cost_per_bf"]

    # Update cost
    new_cost = "9.50"
    response = client.put(
        "/api/v2/catalog/materials/Oak/Standard",
        json={"cost_per_bf": new_cost},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["cost_per_bf"] == new_cost

    # Verify old row was closed (effective_to set)
    old_row = (
        db.query(MaterialCost)
        .filter(
            MaterialCost.wood_species == "Oak",
            MaterialCost.grade == "Standard",
            MaterialCost.effective_to.isnot(None),
        )
        .first()
    )
    assert old_row is not None
    assert old_row.effective_to == date.today()

    # Verify new row is active
    new_row = (
        db.query(MaterialCost)
        .filter(
            MaterialCost.wood_species == "Oak",
            MaterialCost.grade == "Standard",
            MaterialCost.effective_to.is_(None),
        )
        .first()
    )
    assert new_row is not None
    assert str(new_row.cost_per_bf) == new_cost


def test_update_material_cost_requires_admin(client, db):
    """Test that only admins can update material costs."""
    # Create viewer user
    viewer = User(
        email="viewer@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
        full_name="Viewer User",
        role=UserRole.viewer,
        is_active=True,
    )
    db.add(viewer)
    db.commit()

    # Login as viewer
    response = client.post(
        "/api/v2/auth/login",
        data={"username": "viewer@test.com", "password": "password"},
    )
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Try to update cost
    response = client.put(
        "/api/v2/catalog/materials/Oak/Standard",
        json={"cost_per_bf": "10.00"},
        headers=headers,
    )
    assert response.status_code == 403  # Forbidden


def test_get_current_snapshot(client, db):
    """Test retrieving current price book snapshot."""
    # Setup
    admin = User(
        email="admin@test.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5K3M.QFRxJuYi",
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
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get snapshot
    response = client.get("/api/v2/catalog/snapshot/current", headers=headers)
    assert response.status_code == 200
    snapshot = response.json()

    # Should have all required fields
    assert "snapshot_hash" in snapshot
    assert "material_costs" in snapshot
    assert "labor_rates" in snapshot
    assert "overhead_pct" in snapshot
    assert len(snapshot["snapshot_hash"]) == 64  # SHA-256 hex


def test_catalog_requires_authentication(client):
    """Test that catalog endpoints require authentication."""
    # Try to get materials without auth
    response = client.get("/api/v2/catalog/materials")
    assert response.status_code == 401

    # Try to get labor rates without auth
    response = client.get("/api/v2/catalog/labor-rates")
    assert response.status_code == 401
