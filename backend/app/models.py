"""
models.py
---------
The five tables from section 11 of the concept note, written as SQLAlchemy
models. A few extra fields were added where the features needed them
(they are listed in DECISIONS.md).

    User  1---*  Dataset  1---*  AnalysisHistory  1---*  Prediction
                                        1---*  Report

Uploaded data itself is NOT stored in these tables. Every uploaded file gets
its own table inside the "datasets" schema, and Dataset.table_name points to it.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="user")       # "user" or "admin"
    password_hash: Mapped[str] = mapped_column(String(255))             # bcrypt hash, never the password
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    datasets = relationship("Dataset", back_populates="owner", cascade="all, delete-orphan")


class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)   # owner
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(255))            # original file name
    table_name: Mapped[str] = mapped_column(String(80))         # table inside the "datasets" schema
    schema_info: Mapped[dict] = mapped_column(JSON)             # columns, types, sample values
    cleaning_summary: Mapped[dict] = mapped_column(JSON)        # what the cleaning step fixed
    overview: Mapped[dict] = mapped_column(JSON)                # statistics and charts, computed once
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    owner = relationship("User", back_populates="datasets")
    analyses = relationship("AnalysisHistory", back_populates="dataset", cascade="all, delete-orphan")


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    analysis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.dataset_id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    question_key: Mapped[str] = mapped_column(String(500), index=True)  # tidy form of the question, used by the cache
    operation: Mapped[str] = mapped_column(String(30))          # "nl_query" or "forecast"
    status: Mapped[str] = mapped_column(String(30))             # success / clarification / blocked / error
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)     # the insight text
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)       # columns + rows
    chart_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    insight_source: Mapped[str | None] = mapped_column(String(30), nullable=True)   # "llm" or "template"
    model_used: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    dataset = relationship("Dataset", back_populates="analyses")
    predictions = relationship("Prediction", back_populates="analysis", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="analysis", cascade="all, delete-orphan")


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_history.analysis_id"), index=True)
    model_name: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(60))
    output: Mapped[dict] = mapped_column(JSON)                  # the forecast values
    evaluation_reference: Mapped[dict] = mapped_column(JSON)    # MAE and RMSE of every model tried
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis = relationship("AnalysisHistory", back_populates="predictions")


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_history.analysis_id"), index=True)
    report_title: Mapped[str] = mapped_column(String(300))
    generated_content: Mapped[dict] = mapped_column(JSON)       # the text parts of the report
    file_path: Mapped[str] = mapped_column(String(500))         # where the PDF is saved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis = relationship("AnalysisHistory", back_populates="reports")
