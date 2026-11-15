"""
routers/admin.py
----------------
Endpoints that only an admin can use: see all users and all datasets.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dataset, User
from app.schemas import dataset_out, user_out
from app.security import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users", summary="All users (admin only)")
def all_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    # Count each user's datasets in the same query.
    counts = dict(db.execute(select(Dataset.user_id, func.count()).group_by(Dataset.user_id)).all())
    users = db.scalars(select(User).order_by(User.user_id)).all()
    return [{**user_out(u), "dataset_count": counts.get(u.user_id, 0)} for u in users]


@router.get("/datasets", summary="All datasets of all users (admin only)")
def all_datasets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.execute(select(Dataset, User).join(User, Dataset.user_id == User.user_id)
                      .order_by(Dataset.upload_date.desc())).all()
    return [{**dataset_out(dataset), "owner_name": owner.name, "owner_email": owner.email}
            for dataset, owner in rows]
