"""
routers/forecast.py
-------------------
Sales forecast endpoints. Every forecast is saved:
  - one row in Analysis_History (so it shows up in History and can be exported)
  - one row in Prediction (model name, version, forecast values, MAE and RMSE)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_dataset_for_user
from app.models import AnalysisHistory, Dataset, Prediction, User
from app.schemas import ForecastRequest, analysis_out
from app.security import get_current_user
from app.services import forecasting, loader
from app.services.insight import format_number
from app.services.profiling import pick_main_metric

router = APIRouter(prefix="/api/forecast", tags=["Forecast"])


def _column_options(dataset: Dataset) -> dict:
    """Which columns can be forecast, and the default choice."""
    roles = dataset.overview.get("roles", {})
    dates, measures = roles.get("dates", []), roles.get("measures", [])
    return {"date_columns": dates, "value_columns": measures,
            "default_date": dates[0] if dates else None,
            "default_value": pick_main_metric(measures)}


def _prediction_out(prediction: Prediction, analysis: AnalysisHistory, dataset: Dataset) -> dict:
    return {
        "prediction_id": prediction.prediction_id,
        "model_name": prediction.model_name,
        "model_version": prediction.model_version,
        "output": prediction.output,
        "evaluation": prediction.evaluation_reference,
        "created_at": prediction.created_at.isoformat(),
        "analysis": analysis_out(analysis, dataset.name),
    }


@router.get("/options/{dataset_id}", summary="Columns that can be used for a forecast")
def options(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _column_options(get_dataset_for_user(db, dataset_id, user))


@router.get("/latest/{dataset_id}", summary="The most recent saved forecast for a dataset")
def latest(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, dataset_id, user)
    row = db.execute(
        select(Prediction, AnalysisHistory)
        .join(AnalysisHistory, Prediction.analysis_id == AnalysisHistory.analysis_id)
        .where(AnalysisHistory.dataset_id == dataset.dataset_id)
        .order_by(Prediction.created_at.desc()).limit(1)).first()
    if row is None:
        return None
    return _prediction_out(row[0], row[1], dataset)


@router.post("", summary="Run a 3 month forecast and save it")
def create_forecast(body: ForecastRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    dataset = get_dataset_for_user(db, body.dataset_id, user)
    choices = _column_options(dataset)
    date_column = body.date_column or choices["default_date"]
    value_column = body.value_column or choices["default_value"]
    if date_column not in choices["date_columns"] or value_column not in choices["value_columns"]:
        raise HTTPException(status_code=400, detail="A forecast needs one date column and one number "
                                                    "column. This dataset does not have a usable pair.")

    df = loader.load_table(dataset.table_name, dataset.schema_info)
    try:
        series = forecasting.monthly_series(df, date_column, value_column)
        result = forecasting.run_forecast(series)
    except forecasting.ForecastError as error:
        raise HTTPException(status_code=400, detail=str(error))

    value_label = value_column.replace("_", " ").title()
    best = next(s for s in result["scores"] if s["model"] == result["best_model"])
    first, last = result["forecast"][0], result["forecast"][-1]
    summary = (
        f"{result['best_model']} was the most accurate of {len(result['scores'])} models on the "
        f"test period ({result['test_period']}), with MAE {format_number(best['mae'])} and "
        f"RMSE {format_number(best['rmse'])}. It forecasts {value_label.lower()} of "
        f"{format_number(first['value'])} for {first['month'][:7]} and "
        f"{format_number(last['value'])} for {last['month'][:7]}. "
        "A forecast is an estimate from past patterns, not a guarantee.")

    analysis = AnalysisHistory(
        user_id=user.user_id, dataset_id=dataset.dataset_id,
        question=f"Forecast monthly {value_label.lower()} for the next {forecasting.HORIZON_MONTHS} months",
        question_key=f"forecast {date_column} {value_column}", operation="forecast", status="success",
        result_summary=summary, insight_source="template", model_used=result["best_model"], llm_calls=0,
        result_data={"columns": ["month", f"forecast_{value_column}"],
                     "rows": [[f["month"], f["value"]] for f in result["forecast"]],
                     "row_count": len(result["forecast"])},
        chart_spec=forecasting.forecast_chart(result, value_label))
    db.add(analysis)
    db.flush()

    prediction = Prediction(
        analysis_id=analysis.analysis_id, model_name=result["best_model"],
        model_version=result["model_version"],
        output={"date_column": date_column, "value_column": value_column,
                "forecast": result["forecast"], "history": result["history"]},
        evaluation_reference={"metric_note": "Lower is better. Measured on months the models never saw.",
                              "scores": result["scores"], "train_period": result["train_period"],
                              "test_period": result["test_period"], "test": result["test"]})
    db.add(prediction)
    db.commit()
    return _prediction_out(prediction, analysis, dataset)
