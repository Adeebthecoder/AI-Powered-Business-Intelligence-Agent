"""
routers/reports.py
------------------
Create, list and download PDF reports. A report is always made from one saved
analysis (a question and answer, or a forecast).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import STORAGE_DIR
from app.database import get_db
from app.deps import get_analysis_for_user
from app.models import AnalysisHistory, Report, User
from app.schemas import report_out
from app.security import get_current_user
from app.services.report_pdf import build_report_pdf

router = APIRouter(prefix="/api/reports", tags=["Reports"])
REPORTS_DIR = STORAGE_DIR / "reports"


def _report_for_user(db: Session, report_id: int, user: User) -> Report:
    report = db.get(Report, report_id)
    if report is None or (report.analysis.user_id != user.user_id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.post("/{analysis_id}", summary="Create a PDF report from a saved analysis")
def create_report(analysis_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analysis = get_analysis_for_user(db, analysis_id, user)
    if analysis.status != "success":
        raise HTTPException(status_code=400, detail="Only successful answers can be exported as a report.")

    dataset_name = analysis.dataset.name
    title = ("Forecast report" if analysis.operation == "forecast" else "Analysis report") \
        + f": {analysis.question[:120]}"

    # Forecast reports also show how each model scored.
    extra_tables = []
    for prediction in analysis.predictions:
        evaluation = prediction.evaluation_reference
        extra_tables.append({
            "title": "Model comparison on the held-out test period",
            "columns": ["Model", "MAE", "RMSE"],
            "rows": [[s["model"], s["mae"], s["rmse"]] for s in evaluation["scores"]],
            "note": f"Chosen model: {prediction.model_name}, version {prediction.model_version}. "
                    f"Trained on {evaluation['train_period']}, tested on {evaluation['test_period']}. "
                    "Lower MAE and RMSE are better.",
        })

    report = Report(
        analysis_id=analysis.analysis_id, report_title=title, file_path="pending",
        generated_content={"dataset_name": dataset_name, "question": analysis.question,
                           "insight": analysis.result_summary, "sql": analysis.sql_query,
                           "row_count": (analysis.result_data or {}).get("row_count")})
    db.add(report)
    db.flush()                                          # gives us report.report_id

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = REPORTS_DIR / f"report_{report.report_id}.pdf"
    try:
        build_report_pdf(str(pdf_path), title=title, question=analysis.question,
                         dataset_name=dataset_name, insight=analysis.result_summary,
                         sql=analysis.sql_query, result=analysis.result_data,
                         chart=analysis.chart_spec, analysis_time=analysis.timestamp,
                         extra_tables=extra_tables)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create the PDF: {error}")
    report.file_path = pdf_path.name                    # only the file name is stored
    db.commit()
    return report_out(report)


@router.get("", summary="My reports, newest first")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(Report).join(AnalysisHistory, Report.analysis_id == AnalysisHistory.analysis_id)
        .where(AnalysisHistory.user_id == user.user_id).order_by(Report.created_at.desc())).all()
    return [report_out(r) for r in rows]


@router.get("/{report_id}/download", summary="Download the PDF file")
def download_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = _report_for_user(db, report_id, user)
    pdf_path = REPORTS_DIR / Path(report.file_path).name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="The PDF file is missing. Please create the report again.")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"bi_report_{report.report_id}.pdf")


@router.delete("/{report_id}", summary="Delete a report")
def delete_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = _report_for_user(db, report_id, user)
    (REPORTS_DIR / Path(report.file_path).name).unlink(missing_ok=True)
    db.delete(report)
    db.commit()
    return {"message": "Report deleted."}
