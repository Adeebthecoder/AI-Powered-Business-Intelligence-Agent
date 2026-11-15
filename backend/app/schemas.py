"""
schemas.py
----------
Shapes of the data that the API receives (request bodies) and small helper
functions that turn database rows into plain dictionaries for the frontend.
"""

import re

from pydantic import BaseModel, Field, field_validator

from app.models import AnalysisHistory, Dataset, Report, User

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def email_must_look_valid(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.match(value):
            raise ValueError("Please enter a valid email address.")
        return value


class AskRequest(BaseModel):
    dataset_id: int
    question: str = Field(min_length=1, max_length=500)
    # When the system asked a clarifying question, the frontend sends the
    # earlier question here so the LLM has the full picture.
    previous_question: str | None = Field(default=None, max_length=500)
    # Set to true to ignore the saved answer and ask again.
    skip_cache: bool = False


class ForecastRequest(BaseModel):
    dataset_id: int
    # Both are optional. When empty, the system picks the first date column
    # and the main number column (for example revenue).
    date_column: str | None = None
    value_column: str | None = None


# ---------------------------------------------------------------------------
# Database row -> dictionary
# ---------------------------------------------------------------------------

def user_out(user: User) -> dict:
    return {"user_id": user.user_id, "name": user.name, "email": user.email,
            "role": user.role, "created_at": user.created_at.isoformat()}


def dataset_out(dataset: Dataset, detail: bool = False) -> dict:
    data = {
        "dataset_id": dataset.dataset_id, "name": dataset.name, "source": dataset.source,
        "row_count": dataset.row_count, "column_count": dataset.column_count,
        "upload_date": dataset.upload_date.isoformat(), "owner_id": dataset.user_id,
    }
    if detail:
        data["schema_info"] = dataset.schema_info
        data["cleaning_summary"] = dataset.cleaning_summary
    return data


def analysis_out(analysis: AnalysisHistory, dataset_name: str | None = None, cached: bool = False) -> dict:
    return {
        "analysis_id": analysis.analysis_id,
        "dataset_id": analysis.dataset_id,
        "dataset_name": dataset_name,
        "question": analysis.question,
        "operation": analysis.operation,
        "status": analysis.status,
        "sql": analysis.sql_query,
        "insight": analysis.result_summary,
        "insight_source": analysis.insight_source,
        "result": analysis.result_data,
        "chart": analysis.chart_spec,
        "model_used": analysis.model_used,
        "llm_calls": analysis.llm_calls,
        "message": analysis.error_message,
        "cached": cached,
        "timestamp": analysis.timestamp.isoformat(),
    }


def report_out(report: Report) -> dict:
    return {"report_id": report.report_id, "analysis_id": report.analysis_id,
            "report_title": report.report_title, "created_at": report.created_at.isoformat(),
            "dataset_name": (report.generated_content or {}).get("dataset_name")}
