"""
routers/datasets.py
-------------------
Upload, list, view and delete datasets, plus the automatic overview.

Upload runs the whole data pipeline:
    read file -> clean -> save as its own PostgreSQL table -> save schema -> build overview
"""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import DATASET_SCHEMA, STORAGE_DIR, get_settings
from app.database import app_engine, get_db
from app.deps import get_dataset_for_user
from app.models import Dataset, User
from app.schemas import dataset_out
from app.security import get_current_user
from app.services import loader
from app.services.cleaning import clean_dataframe, read_uploaded_file
from app.services.overview import build_overview
from app.services.profiling import build_schema_info, to_plain

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])
settings = get_settings()

ALLOWED_EXTENSIONS = (".csv", ".xlsx")


@router.post("", summary="Upload a CSV or Excel file")
def upload_dataset(file: UploadFile = File(...), name: str = Form(default=""),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    filename = Path(file.filename or "upload").name
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload a CSV (.csv) or Excel (.xlsx) file.")

    content = file.file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413,
                            detail=f"The file is larger than {settings.max_upload_mb} MB.")
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty.")

    # Pandas reads from a file on disk, so save the upload to a temporary file first.
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as temp:
        temp.write(content)
        temp_path = temp.name
    try:
        raw = read_uploaded_file(temp_path, filename)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not read the file: {error}")
    finally:
        os.remove(temp_path)

    if raw.empty or raw.shape[1] == 0:
        raise HTTPException(status_code=400, detail="The file has no data rows.")

    # ---- Clean -------------------------------------------------------------
    clean, cleaning_summary = clean_dataframe(raw)
    if clean.empty:
        raise HTTPException(status_code=400, detail="No usable rows were left after cleaning.")

    # ---- Save the dataset record (to get its id), then the data table --------
    dataset_name = name.strip() or Path(filename).stem.replace("_", " ").title()
    dataset = Dataset(
        user_id=user.user_id, name=dataset_name[:200], source=filename, table_name="pending",
        schema_info=build_schema_info(clean), cleaning_summary=cleaning_summary,
        overview=build_overview(clean, cleaning_summary),
        row_count=int(len(clean)), column_count=int(clean.shape[1]),
    )
    db.add(dataset)
    db.flush()                                        # gives us dataset.dataset_id
    dataset.table_name = loader.make_table_name(dataset.dataset_id, dataset_name)
    try:
        loader.save_table(clean, dataset.table_name)
    except Exception as error:
        db.rollback()
        loader.drop_table(dataset.table_name)
        raise HTTPException(status_code=500, detail=f"Could not save the data to the database: {error}")
    db.commit()
    return dataset_out(dataset, detail=True)


@router.get("", summary="List my datasets")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Dataset).where(Dataset.user_id == user.user_id)
                      .order_by(Dataset.upload_date.desc())).all()
    return [dataset_out(d) for d in rows]


@router.get("/{dataset_id}", summary="One dataset with its schema and cleaning summary")
def get_dataset(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return dataset_out(get_dataset_for_user(db, dataset_id, user), detail=True)


@router.get("/{dataset_id}/overview", summary="Automatic overview: KPIs, statistics and charts")
def get_overview(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, dataset_id, user)
    return {"dataset": dataset_out(dataset, detail=True), "overview": dataset.overview}


@router.get("/{dataset_id}/preview", summary="First rows of the clean data")
def preview(dataset_id: int, limit: int = 20, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, dataset_id, user)
    limit = max(1, min(limit, 100))
    query = text(f'SELECT * FROM "{DATASET_SCHEMA}"."{dataset.table_name}" LIMIT :limit')
    with app_engine.connect() as connection:
        result = connection.execute(query, {"limit": limit})
        columns = list(result.keys())
        rows = [[to_plain(v) for v in row] for row in result.fetchall()]
    return {"columns": columns, "rows": rows}


@router.delete("/{dataset_id}", summary="Delete a dataset and its history")
def delete_dataset(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, dataset_id, user)
    # Remove the PDF files of this dataset's reports from disk.
    for analysis in dataset.analyses:
        for report in analysis.reports:
            (STORAGE_DIR / "reports" / Path(report.file_path).name).unlink(missing_ok=True)
    loader.drop_table(dataset.table_name)
    db.delete(dataset)          # history, predictions and reports are deleted with it
    db.commit()
    return {"message": "Dataset deleted."}
