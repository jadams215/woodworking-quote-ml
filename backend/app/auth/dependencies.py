"""
FastAPI dependencies for authentication and authorization.

Usage in route handlers::

    @router.get("/quotes")
    def list_quotes(user: User = Depends(get_current_user)):
        ...

    @router.post("/admin/users")
    def create_user(user: User = Depends(require_admin)):
        ...

    @router.post("/quotes")
    def create_quote(user: User = Depends(require_estimator_or_admin)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the JWT bearer token and return the authenticated User.

    Raises ``HTTPException(401)`` if the token is invalid/expired or if the
    user record is missing or deactivated.
    """
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require that the authenticated user has the ``admin`` role.

    Raises ``HTTPException(403)`` otherwise.
    """
    if user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_estimator_or_admin(user: User = Depends(get_current_user)) -> User:
    """Require ``estimator`` or ``admin`` role.

    Viewers can read data but cannot create or modify quotes.
    Raises ``HTTPException(403)`` if the user is a viewer.
    """
    if user.role.value not in ("admin", "estimator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Estimator or admin access required",
        )
    return user
