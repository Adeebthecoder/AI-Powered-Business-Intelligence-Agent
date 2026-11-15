"""
routers/ask.py
--------------
The question endpoint, plus two small helpers for the Ask page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_dataset_for_user
from app.models import User
from app.schemas import AskRequest, analysis_out
from app.security import get_current_user
from app.services import llm_client, mock_llm
from app.services.ask_engine import answer_question

router = APIRouter(prefix="/api/ask", tags=["Ask"])


@router.post("", summary="Ask a question in plain English")
def ask(body: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Returns one analysis record. Look at its `status`:
    - `success`: `result`, `chart`, `insight` and `sql` are filled in
    - `clarification`: the system asks a question back (in `message`)
    - `blocked`: the SQL failed the safety check and was not run
    - `error`: a friendly explanation is in `message`
    """
    dataset = get_dataset_for_user(db, body.dataset_id, user)
    record, cached = answer_question(db, user, dataset, body.question,
                                     body.previous_question, body.skip_cache)
    return analysis_out(record, dataset.name, cached=cached)


@router.get("/suggestions/{dataset_id}", summary="Example questions for a dataset")
def suggestions(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, dataset_id, user)
    columns = {c["name"] for c in dataset.schema_info["columns"]}
    if mock_llm.REQUIRED_COLUMNS.issubset(columns):
        # The sample retail dataset: offer the tested demo questions.
        picks = ["Which region had the highest revenue last quarter?",
                 "Compare revenue and profit by product category",
                 "Show the monthly revenue trend",
                 "What are the top 5 products by revenue?",
                 "What is the average discount for each product category?",
                 "What is the total revenue?"]
        return {"questions": picks, "all_mock_questions": mock_llm.supported_questions()}

    # Any other dataset: build simple questions from its own columns.
    roles = dataset.overview.get("roles", {})
    metric = dataset.overview.get("main_metric")
    questions = []
    if metric:
        questions.append(f"What is the total {metric.replace('_', ' ')}?")
        for category in roles.get("categories", [])[:2]:
            questions.append(f"Show total {metric.replace('_', ' ')} by {category.replace('_', ' ')}")
        if roles.get("dates"):
            questions.append(f"Show the monthly {metric.replace('_', ' ')} trend")
    questions.append("How many rows are there?")
    return {"questions": questions, "all_mock_questions": []}


@router.get("/usage", summary="LLM mode and how much of the free quota is used")
def usage(user: User = Depends(get_current_user)):
    return llm_client.usage_status()
