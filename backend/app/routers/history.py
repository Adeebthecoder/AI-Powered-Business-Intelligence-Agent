"""
routers/history.py
------------------
Past questions and answers (the Analysis_History table).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_analysis_for_user
from app.models import AnalysisHistory, Dataset, User
from app.schemas import analysis_out
from app.security import get_current_user

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("", summary="My past questions, newest first")
def list_history(dataset_id: int | None = None, limit: int = 100,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = (select(AnalysisHistory, Dataset.name)
             .join(Dataset, AnalysisHistory.dataset_id == Dataset.dataset_id)
             .where(AnalysisHistory.user_id == user.user_id)
             .order_by(AnalysisHistory.timestamp.desc())
             .limit(max(1, min(limit, 300))))
    if dataset_id is not None:
        query = query.where(AnalysisHistory.dataset_id == dataset_id)
    items = []
    for analysis, dataset_name in db.execute(query).all():
        item = analysis_out(analysis, dataset_name)
        # The list stays light: the full table and chart are loaded when one item is opened.
        item["row_count"] = (analysis.result_data or {}).get("row_count")
        item.pop("result")
        item.pop("chart")
        items.append(item)
    return items


@router.get("/{analysis_id}", summary="One past answer in full")
def get_history_item(analysis_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    analysis = get_analysis_for_user(db, analysis_id, user)
    return analysis_out(analysis, analysis.dataset.name)


@router.delete("/{analysis_id}", summary="Delete one history item")
def delete_history_item(analysis_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    analysis = get_analysis_for_user(db, analysis_id, user)
    db.delete(analysis)
    db.commit()
    return {"message": "History item deleted."}
