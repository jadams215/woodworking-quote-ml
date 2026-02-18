"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.auth.jwt import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserRead
from app.services.audit_service import log_action
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/api/v2/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Login with email and password to receive JWT token.

    OAuth2 password flow compatible (username field = email).
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token
    access_token = create_access_token(user.id, user.role.value)

    # Log successful login
    log_action(
        db,
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=str(user.id),
        old_values=None,
        new_values=None,
    )
    db.commit()

    return TokenResponse(access_token=access_token)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Register a new user (admin only).

    Creates user with hashed password and specified role.
    """
    try:
        user = register_user(db, data)

        # Log user creation
        log_action(
            db,
            user_id=current_user.id,
            action="create_user",
            entity_type="user",
            entity_id=str(user.id),
            old_values=None,
            new_values={"email": user.email, "role": user.role.value},
        )
        db.commit()

        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/me", response_model=UserRead)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.

    Returns user profile from JWT token.
    """
    return current_user
