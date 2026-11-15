"""
forecasting.py
--------------
Monthly forecast for the next 3 months (for example monthly revenue).

Three simple approaches are compared fairly:

  1. Moving average          the average of the last 3 months
  2. Seasonal naive          the same month one year earlier
  3. Linear regression       a straight-line trend plus a "which month is it"
                             effect (scikit-learn)

How the comparison works (and how we avoid leaking future data):
  - The monthly series is split by TIME. The last months are held out as the
    test period. Models are fitted ONLY on the months before it.
  - Each model predicts the test months. We measure MAE and RMSE.
  - The model with the lowest RMSE wins. Only then is the winner fitted again
    on all months to forecast the 3 months after the data ends.
  - The only inputs are the month number and the calendar month, which are
    always known in advance. No value from a future month is ever used.

A last month that is not complete in the data is left out, because half a
month of sales would look like a sudden drop.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

MODEL_VERSION = "1.0"
HORIZON_MONTHS = 3
MIN_MONTHS = 15                    # at least 12 to train on + 3 to test on


class ForecastError(Exception):
    """A problem the user can understand and fix (shown on screen)."""


# ---------------------------------------------------------------------------
# Building the monthly series
# ---------------------------------------------------------------------------

def monthly_series(df: pd.DataFrame, date_column: str, value_column: str) -> pd.Series:
    """Add up the value column per calendar month. Drops an unfinished last month."""
    data = df[[date_column, value_column]].dropna()
    if data.empty:
        raise ForecastError("There is no data in the chosen columns.")
    series = data.set_index(date_column)[value_column].resample("MS").sum().astype(float)

    last_day = data[date_column].max()
    month_end = last_day + pd.offsets.MonthEnd(0)
    if (month_end - last_day).days > 2:            # the last month stops early in the data
        series = series.iloc[:-1]
    return series


# ---------------------------------------------------------------------------
# The three models. Each takes the training series and the number of months
# to predict, and returns that many predictions.
# ---------------------------------------------------------------------------

def moving_average(train: pd.Series, steps: int) -> np.ndarray:
    return np.repeat(train.iloc[-3:].mean(), steps)


def seasonal_naive(train: pd.Series, steps: int) -> np.ndarray:
    # Month t is predicted with the value of month t-12 (taken from training data only).
    last_year = train.iloc[-12:].to_numpy()
    return np.array([last_year[i % 12] for i in range(steps)])


def _features(month_index: np.ndarray, calendar_month: np.ndarray, use_season: bool) -> np.ndarray:
    """Inputs for the regression: the month counter, and 11 yes/no columns for Feb..Dec."""
    columns = [month_index.reshape(-1, 1)]
    if use_season:
        columns.append((calendar_month.reshape(-1, 1) == np.arange(2, 13)).astype(float))
    return np.hstack(columns)


def linear_regression(train: pd.Series, steps: int) -> np.ndarray:
    n = len(train)
    use_season = n >= 24                           # need 2 examples of each month for the month effect
    future_dates = pd.date_range(train.index[-1] + pd.offsets.MonthBegin(1), periods=steps, freq="MS")
    model = LinearRegression()
    model.fit(_features(np.arange(n), train.index.month.to_numpy(), use_season), train.to_numpy())
    return model.predict(_features(np.arange(n, n + steps), future_dates.month.to_numpy(), use_season))


MODELS = {
    "Moving average (last 3 months)": moving_average,
    "Seasonal naive (same month last year)": seasonal_naive,
    "Linear regression (trend + month effect)": linear_regression,
}


# ---------------------------------------------------------------------------
# Compare, choose, forecast
# ---------------------------------------------------------------------------

def run_forecast(series: pd.Series) -> dict:
    """
    Compare the models on a held-out test period, pick the best one and
    forecast the next HORIZON_MONTHS months.
    """
    n = len(series)
    if n < MIN_MONTHS:
        raise ForecastError(f"Forecasting needs at least {MIN_MONTHS} full months of data. "
                            f"This dataset has {n}.")

    # Hold out the last 6 months for testing (3 if the series is short).
    test_size = 6 if n >= 30 else 3
    train, test = series.iloc[:-test_size], series.iloc[-test_size:]

    scores, test_predictions = [], {}
    for name, model in MODELS.items():
        predicted = model(train, test_size)                    # fitted on train only
        test_predictions[name] = [round(float(v), 2) for v in predicted]
        scores.append({
            "model": name,
            "mae": round(float(mean_absolute_error(test, predicted)), 2),
            "rmse": round(float(np.sqrt(mean_squared_error(test, predicted))), 2),
        })
    best = min(scores, key=lambda s: s["rmse"])

    # Fit the winner again on ALL months and predict the months after the data ends.
    future = MODELS[best["model"]](series, HORIZON_MONTHS)
    future_dates = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1),
                                 periods=HORIZON_MONTHS, freq="MS")

    def month_label(d):
        return d.strftime("%Y-%m-%d")

    return {
        "best_model": best["model"],
        "model_version": f"{MODEL_VERSION} (data up to {series.index[-1]:%b %Y})",
        "scores": scores,
        "train_period": f"{train.index[0]:%b %Y} to {train.index[-1]:%b %Y}",
        "test_period": f"{test.index[0]:%b %Y} to {test.index[-1]:%b %Y}",
        "history": [{"month": month_label(d), "value": round(float(v), 2)} for d, v in series.items()],
        "test": {"months": [month_label(d) for d in test.index],
                 "actual": [round(float(v), 2) for v in test],
                 "predictions": test_predictions},
        "forecast": [{"month": month_label(d), "value": round(float(max(v, 0)), 2)}
                     for d, v in zip(future_dates, future)],
    }


def forecast_chart(result: dict, value_label: str) -> dict:
    """A line chart: past months, then the forecast as a second line that joins on."""
    months = [h["month"] for h in result["history"]] + [f["month"] for f in result["forecast"]]
    actual = [h["value"] for h in result["history"]] + [None] * len(result["forecast"])
    # The forecast line starts at the last real month so the two lines connect.
    forecast = [None] * (len(result["history"]) - 1) + [result["history"][-1]["value"]] \
        + [f["value"] for f in result["forecast"]]
    return {"type": "line", "title": f"Monthly {value_label}: history and 3 month forecast",
            "x_label": "Month", "y_label": value_label, "x": months,
            "series": [{"name": "Actual", "values": actual},
                       {"name": "Forecast", "values": forecast, "dashed": True}]}
