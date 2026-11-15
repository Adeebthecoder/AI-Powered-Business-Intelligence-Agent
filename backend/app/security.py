"""
security.py
-----------
Passwords and login tokens.

  - Passwords are hashed with bcrypt. The real password is never stored.
  - After login the user gets a JWT token. The frontend sends it with every
    request in the "Authorization: Bearer <token>" header.
  - get_current_user and require_admin are FastAPI dependencies that protect
    the endpoints.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

settings = get_settings()
JWT_ALGORITHM = "HS256"

# Tells FastAPI (and the /docs page) where the login endpoint is.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.user_id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Reads the token, checks it, and returns the logged-in user."""
    login_again = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise login_again
    user = db.get(User, user_id)
    if user is None:
        raise login_again
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Use this dependency on endpoints that only an admin may call."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can do this.")
    return user
