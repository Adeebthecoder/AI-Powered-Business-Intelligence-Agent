"""
profiling.py
------------
Looks at a clean table and describes it:

  - build_schema_info()  the column list that is saved with the dataset and
                         later sent to the LLM (names, types, a few examples)
  - column_roles()       which columns are dates, measures (numbers we can
                         add up), categories (text with few values) or ids
  - to_plain()           turns Pandas / NumPy values into plain Python values
                         that can be saved as JSON
"""

import math
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

# A text column with at most this many different values is a "category".
MAX_CATEGORY_VALUES = 30
# For small categories we remember the exact values, so the LLM spells them right.
MAX_LISTED_VALUES = 15

# Words that suggest a column is the main business number, best first.
METRIC_KEYWORDS = ["revenue", "sales", "amount", "total", "profit", "income", "price", "quantity", "qty"]


def to_plain(value):
    """Convert one value into something JSON can store."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        # Show dates without a time when the time is midnight.
        return value.strftime("%Y-%m-%d") if value.time().isoformat() == "00:00:00" else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating, Decimal)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return round(number, 4)
    if isinstance(value, (int, str)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def column_kind(series: pd.Series) -> str:
    """Simple type name used across the app: integer, decimal, date, boolean or text."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_numeric_dtype(series):
        return "decimal"
    return "text"


def is_id_like(name: str, series: pd.Series) -> bool:
    """Order ids, customer ids and similar. We never add these up or chart them."""
    lower = name.lower()
    if lower == "id" or lower.endswith("_id") or lower.endswith("_no") or lower.endswith("_code"):
        return True
    if column_kind(series) == "text" and len(series) > 50:
        return series.nunique() > 0.5 * len(series)
    return False


def column_roles(df: pd.DataFrame) -> dict:
    """Sort the columns into dates, measures, categories and ids."""
    roles = {"dates": [], "measures": [], "categories": [], "ids": []}
    for name in df.columns:
        series = df[name]
        kind = column_kind(series)
        if is_id_like(name, series):
            roles["ids"].append(name)
        elif kind == "date":
            roles["dates"].append(name)
        elif kind in ("integer", "decimal"):
            roles["measures"].append(name)
        elif kind == "text" and series.nunique() <= MAX_CATEGORY_VALUES:
            roles["categories"].append(name)
    return roles


def pick_main_metric(measures: list[str]) -> str | None:
    """Choose the most important number column, for example 'revenue'."""
    for keyword in METRIC_KEYWORDS:
        for name in measures:
            if keyword in name.lower():
                return name
    return measures[0] if measures else None


def build_schema_info(df: pd.DataFrame) -> dict:
    """
    Describe every column. This is saved in Dataset.schema_info.

    The LLM only ever sees this description and three sample rows. It never
    sees the full data.
    """
    columns = []
    for name in df.columns:
        series = df[name]
        kind = column_kind(series)
        info = {
            "name": name,
            "type": kind,
            "distinct_values": int(series.nunique()),
            "examples": [to_plain(v) for v in series.dropna().unique()[:3]],
        }
        if kind in ("integer", "decimal", "date") and series.notna().any():
            info["min"] = to_plain(series.min())
            info["max"] = to_plain(series.max())
        if kind == "text" and info["distinct_values"] <= MAX_LISTED_VALUES:
            info["values"] = sorted(str(v) for v in series.dropna().unique())
        columns.append(info)

    sample_rows = [{k: to_plain(v) for k, v in row.items()}
                   for row in df.head(3).to_dict(orient="records")]
    return {"columns": columns, "sample_rows": sample_rows, "row_count": int(len(df))}
