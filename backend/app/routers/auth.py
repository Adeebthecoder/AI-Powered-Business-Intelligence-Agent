"""
routers/auth.py
---------------
Signup, login and "who am I" endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import SignupRequest, user_out
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/signup", summary="Create a new account")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    # New accounts always get the normal "user" role. Admins are created from the .env file.
    user = User(name=body.name.strip(), email=body.email, role="user",
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_out(user)}


@router.post("/login", summary="Log in with email and password")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # The standard login form calls the field "username". We use the email in it.
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_out(user)}


@router.get("/me", summary="Details of the logged-in user")
def me(user: User = Depends(get_current_user)):
    return user_out(user)
