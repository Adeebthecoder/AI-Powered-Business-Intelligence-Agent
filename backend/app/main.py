"""
main.py
-------
Starting point of the backend.

Start it from the "backend" folder with:
    uvicorn app.main:app --reload

Then open http://localhost:8000/docs to see and try every endpoint.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import APP_NAME, CREDIT_LINE, STORAGE_DIR, get_settings
from app.database import Base, SessionLocal, app_engine
from app.models import User
from app.routers import admin, ask, auth, datasets, forecast, history, reports
from app.security import hash_password

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bi_agent")


def create_default_accounts():
    """Create the demo user and the admin from the .env file, if they do not exist yet."""
    accounts = [
        ("Demo User", settings.demo_user_email, settings.demo_user_password, "user"),
        ("Admin", settings.admin_email, settings.admin_password, "admin"),
    ]
    with SessionLocal() as db:
        for name, email, password, role in accounts:
            if not email or not password:
                continue                    # left empty in .env, so skip this account
            email = email.strip().lower()
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(name=name, email=email, role=role, password_hash=hash_password(password)))
                logger.info("Created default %s account: %s", role, email)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        Base.metadata.create_all(app_engine)        # create the five tables if missing
        create_default_accounts()
    except OperationalError as error:
        raise SystemExit(
            "\nCould not connect to PostgreSQL.\n"
            "1. Check that PostgreSQL is running.\n"
            "2. Check DB_HOST and DB_PORT in the .env file.\n"
            "3. Run:  python scripts/setup_database.py\n\n"
            f"Details: {error.orig}\n")
    logger.info("LLM mode: %s", "mock (no API calls)" if settings.is_mock else f"live ({settings.llm_model})")
    yield


app = FastAPI(
    title=APP_NAME,
    description=("Upload business data, ask questions in plain English, and get safe SQL, "
                 f"charts and short insights.\n\n{CREDIT_LINE}"),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the React frontend (a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    """Last safety net: never show a raw crash to the user."""
    logger.exception("Unexpected error on %s", request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Something went wrong on the server. Please try again."})


@app.get("/api/health", tags=["Health"], summary="Check that the backend is running")
def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "llm_mode": "mock" if settings.is_mock else "live",
        "llm_model": None if settings.is_mock else settings.llm_model,
        "credit": CREDIT_LINE,
    }


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(ask.router)
app.include_router(history.router)
app.include_router(forecast.router)
app.include_router(reports.router)
app.include_router(admin.router)
