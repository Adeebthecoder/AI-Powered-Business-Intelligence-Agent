"""
database.py
-----------
Database connections.

There are TWO connections to the same PostgreSQL database:

  app_engine       logs in as the app user. Used for normal work: users,
                   history, loading uploaded files.

  readonly_engine  logs in as the read-only user. Used ONLY to run the SQL
                   that the AI wrote. Even if a bad query got past our checks,
                   this user has no permission to change or delete anything.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

app_engine = create_engine(settings.app_database_url, pool_pre_ping=True)
readonly_engine = create_engine(settings.readonly_database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Parent class of all table models in models.py."""


def get_db():
    """FastAPI dependency: gives each request its own database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
