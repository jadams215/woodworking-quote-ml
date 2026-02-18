"""Unit tests for authentication."""
import pytest
from jose import jwt

from app.auth.jwt import create_access_token, decode_token
from app.auth.password import hash_password, verify_password
from app.config import get_settings

settings = get_settings()


def test_password_hashing():
    """Test password hashing and verification."""
    password = "SecurePassword123!"

    # Hash password
    hashed = hash_password(password)

    # Should not be plain text
    assert hashed != password
    assert len(hashed) > 0

    # Should verify correctly
    assert verify_password(password, hashed) is True

    # Should reject wrong password
    assert verify_password("WrongPassword", hashed) is False


def test_password_hash_uniqueness():
    """Test that same password produces different hashes (salt)."""
    password = "SamePassword123"

    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Different hashes due to random salt
    assert hash1 != hash2

    # Both should verify
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


def test_jwt_creation_and_decoding():
    """Test JWT token creation and decoding."""
    from uuid import uuid4

    user_id = uuid4()
    role = "admin"

    # Create token
    token = create_access_token(user_id, role)

    assert isinstance(token, str)
    assert len(token) > 0

    # Decode token
    payload = decode_token(token)

    assert payload.user_id == user_id
    assert payload.role == role
    assert payload.exp is not None


def test_jwt_invalid_token():
    """Test that invalid tokens are rejected."""
    invalid_token = "invalid.token.here"

    with pytest.raises(Exception):  # Should raise jwt.JWTError or similar
        decode_token(invalid_token)


def test_jwt_expired_token():
    """Test that expired tokens are rejected."""
    from datetime import timedelta
    from uuid import uuid4

    user_id = uuid4()
    role = "viewer"

    # Create token that expires immediately
    token = create_access_token(user_id, role, expires_delta=timedelta(seconds=-1))

    # Should fail to decode due to expiration
    with pytest.raises(Exception):
        decode_token(token)


def test_jwt_tampered_token():
    """Test that tampered tokens are rejected."""
    from uuid import uuid4

    user_id = uuid4()
    role = "viewer"

    # Create valid token
    token = create_access_token(user_id, role)

    # Tamper with token by changing a character
    tampered = token[:-5] + "XXXXX"

    # Should fail to decode
    with pytest.raises(Exception):
        decode_token(tampered)


def test_jwt_role_in_token():
    """Test that role is correctly encoded in token."""
    from uuid import uuid4

    user_id = uuid4()

    # Test all roles
    for role in ["admin", "estimator", "viewer"]:
        token = create_access_token(user_id, role)
        payload = decode_token(token)
        assert payload.role == role
