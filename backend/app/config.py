"""
config.py
---------
Reads every setting from the ".env" file in the project folder.

No secret has a default value here. If a required value is missing, the app
stops at startup with a clear message instead of running with a weak default.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the project folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"

# Folder for files the app creates while running (PDF reports, logs, counters).
STORAGE_DIR = BACKEND_DIR / "storage"

# Text that must appear in the app, the README and every report.
CREDIT_LINE = "Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project"
APP_NAME = "AI-Powered Business Intelligence Agent"

# PostgreSQL schema that holds one table per uploaded dataset.
DATASET_SCHEMA = "dataset_tables"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    # ----- LLM -----
    llm_mode: str = "mock"                      # "mock" or "live"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = ""
    llm_fallback_model: str = ""
    llm_max_calls_per_minute: int = 20
    llm_max_calls_per_day: int = 50

    # ----- Database (required, no defaults for passwords) -----
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "bi_agent"
    db_app_user: str = "bi_app"
    db_app_password: str
    db_readonly_user: str = "bi_readonly"
    db_readonly_password: str
    postgres_superuser: str = "postgres"
    postgres_superuser_password: str = ""

    # ----- Login -----
    jwt_secret: str
    jwt_expire_minutes: int = 480

    # ----- Demo accounts (skipped when left empty) -----
    demo_user_email: str = ""
    demo_user_password: str = ""
    admin_email: str = ""
    admin_password: str = ""

    # ----- Safety and limits -----
    sql_max_rows: int = 1000
    sql_timeout_seconds: int = 10
    max_upload_mb: int = 20
    frontend_origin: str = "http://localhost:5173"

    def _url(self, user: str, password: str) -> str:
        # quote_plus keeps special characters in a password from breaking the URL
        return (f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}")

    @property
    def app_database_url(self) -> str:
        return self._url(self.db_app_user, self.db_app_password)

    @property
    def readonly_database_url(self) -> str:
        return self._url(self.db_readonly_user, self.db_readonly_password)

    @property
    def is_mock(self) -> bool:
        return self.llm_mode.strip().lower() != "live"


@lru_cache
def get_settings() -> Settings:
    """Load the settings once and reuse them everywhere."""
    try:
        return Settings()
    except Exception as error:  # missing values in .env
        raise SystemExit(
            "\nCould not load settings from the .env file.\n"
            "Run this first from the backend folder:  python scripts/make_env.py\n\n"
            f"Details: {error}\n"
        )
