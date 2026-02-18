"""Authentication service for user registration and login."""
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import UserCreate


def register_user(db: Session, data: UserCreate) -> User:
    """
    Register a new user (admin only operation).

    Args:
        db: Database session
        data: User creation data

    Returns:
        Created User instance

    Raises:
        ValueError: If email already exists
    """
    # Check if email already exists
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise ValueError(f"User with email {data.email} already exists")

    # Create user with hashed password
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """
    Authenticate user with email and password.

    Args:
        db: Database session
        email: User email
        password: Plain text password

    Returns:
        User if authenticated, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
