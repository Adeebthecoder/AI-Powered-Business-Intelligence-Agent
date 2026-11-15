"""
deps.py
-------
Small helpers shared by the routers. They load a record and check that the
logged-in user is allowed to see it. A normal user can only reach their own
data. An admin can reach everything.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AnalysisHistory, Dataset, User


def get_dataset_for_user(db: Session, dataset_id: int, user: User) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    # The same "not found" message is used for "does not exist" and "not yours",
    # so nobody can find out which dataset ids exist.
    if dataset is None or (dataset.user_id != user.user_id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


def get_analysis_for_user(db: Session, analysis_id: int, user: User) -> AnalysisHistory:
    analysis = db.get(AnalysisHistory, analysis_id)
    if analysis is None or (analysis.user_id != user.user_id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return analysis
