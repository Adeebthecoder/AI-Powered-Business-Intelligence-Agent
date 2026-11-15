"""
time_reference.py
-----------------
Works out what "last quarter", "last month" and "this year" mean for a dataset.

Important choice: these words are measured from the LATEST DATE IN THE DATA,
not from today's date. The sample data ends in December 2025. If we used
today's date, "last quarter" would point at months that have no data at all.

"Last quarter" means the most recent COMPLETE calendar quarter in the data.
"""

from datetime import date, timedelta


def _quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def build_time_reference(schema_info: dict) -> dict | None:
    """
    Returns, for the first date column of the dataset:
        {"date_column": "order_date", "data_start": "2023-01-01", "data_end": "2025-12-31",
         "last_quarter_start": "2025-10-01", "last_quarter_end": "2025-12-31", "last_quarter_name": "Q4 2025",
         "last_month_start": "2025-12-01", "last_month_end": "2025-12-31",
         "this_year": 2025, "last_year": 2024}
    or None if the dataset has no date column.
    """
    date_columns = [c for c in schema_info.get("columns", []) if c["type"] == "date" and c.get("max")]
    if not date_columns:
        return None
    column = date_columns[0]
    latest = date.fromisoformat(str(column["max"])[:10])

    # --- last complete quarter ---
    quarter_start = _quarter_start(latest)
    quarter_end = _next_month(_next_month(_next_month(quarter_start))) - timedelta(days=1)
    if latest < quarter_end:                      # the newest quarter is not finished yet
        quarter_end = quarter_start - timedelta(days=1)
        quarter_start = _quarter_start(quarter_end)

    # --- last complete month ---
    month_start = date(latest.year, latest.month, 1)
    month_end = _next_month(month_start) - timedelta(days=1)
    if latest < month_end:
        month_end = month_start - timedelta(days=1)
        month_start = date(month_end.year, month_end.month, 1)

    return {
        "date_column": column["name"],
        "data_start": str(column["min"])[:10],
        "data_end": latest.isoformat(),
        "last_quarter_start": quarter_start.isoformat(),
        "last_quarter_end": quarter_end.isoformat(),
        "last_quarter_name": f"Q{(quarter_start.month - 1) // 3 + 1} {quarter_start.year}",
        "last_month_start": month_start.isoformat(),
        "last_month_end": month_end.isoformat(),
        "this_year": latest.year,
        "last_year": latest.year - 1,
    }
