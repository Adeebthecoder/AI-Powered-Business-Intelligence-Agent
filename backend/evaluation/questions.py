"""
evaluation/questions.py
-----------------------
20 business questions about the sample retail dataset, each with the correct
answer computed DIRECTLY IN PANDAS (no SQL, no LLM). These are the "answer
key" that run_evaluation.py marks the system against.

Each question has:
    question   the text sent to the system
    kind       how the answer is compared:
                 "number"  one number (for example total revenue)
                 "label"   one name that must be in the first row (for example "West")
                 "pairs"   a list of (name, number) that must all appear
                 "ranked"  like "pairs", but the rows must also be in this order
    expected   a function that takes the clean Pandas table and returns the answer
"""

import pandas as pd


def _last_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """Rows in the most recent complete quarter of the data (worked out in Pandas)."""
    latest = df["order_date"].max()
    quarter = latest.to_period("Q")
    if latest.normalize() < quarter.end_time.normalize():
        quarter -= 1                                   # newest quarter is not finished
    return df[(df["order_date"] >= quarter.start_time) & (df["order_date"] <= quarter.end_time)]


def _pairs(series: pd.Series, digits: int = 2) -> list:
    """Turn a Pandas result into [(name, number), ...]."""
    return [(str(name), round(float(value), digits)) for name, value in series.items()]


def _monthly_2025(df):
    rows = df[df["order_date"].dt.year == 2025]
    monthly = rows.groupby(rows["order_date"].dt.strftime("%Y-%m"))["revenue"].sum()
    return _pairs(monthly)


def _margin(df):
    grouped = df.groupby("product_category")[["profit", "revenue"]].sum()
    return _pairs(grouped["profit"] / grouped["revenue"] * 100)


QUESTIONS = [
    {"question": "What is the total revenue?", "kind": "number",
     "expected": lambda df: df["revenue"].sum()},
    {"question": "What is the total profit?", "kind": "number",
     "expected": lambda df: df["profit"].sum()},
    {"question": "How many orders are there?", "kind": "number",
     "expected": lambda df: len(df)},
    {"question": "What is the average order value?", "kind": "number",
     "expected": lambda df: df["revenue"].mean()},
    {"question": "How many unique customers are there?", "kind": "number",
     "expected": lambda df: df["customer_id"].nunique()},

    {"question": "Which region had the highest revenue last quarter?", "kind": "label",
     "expected": lambda df: _last_quarter(df).groupby("region")["revenue"].sum().idxmax()},
    {"question": "Show total revenue by region", "kind": "pairs",
     "expected": lambda df: _pairs(df.groupby("region")["revenue"].sum())},
    {"question": "Which product category has the highest revenue?", "kind": "label",
     "expected": lambda df: df.groupby("product_category")["revenue"].sum().idxmax()},
    {"question": "Which product category has the lowest profit?", "kind": "label",
     "expected": lambda df: df.groupby("product_category")["profit"].sum().idxmin()},
    {"question": "Show monthly revenue for 2025", "kind": "pairs",
     "expected": _monthly_2025},

    {"question": "Show total revenue by year", "kind": "pairs",
     "expected": lambda df: _pairs(df.groupby(df["order_date"].dt.year)["revenue"].sum())},
    {"question": "What are the top 5 products by revenue?", "kind": "ranked",
     "expected": lambda df: _pairs(df.groupby("product_name")["revenue"].sum().nlargest(5))},
    {"question": "What are the top 5 cities by revenue?", "kind": "ranked",
     "expected": lambda df: _pairs(df.groupby("city")["revenue"].sum().nlargest(5))},
    {"question": "What is the average discount for each product category?", "kind": "pairs",
     "expected": lambda df: _pairs(df.groupby("product_category")["discount"].mean(), digits=4)},
    {"question": "Which payment mode is used the most?", "kind": "label",
     "expected": lambda df: df["payment_mode"].value_counts().idxmax()},

    {"question": "Show revenue by customer segment", "kind": "pairs",
     "expected": lambda df: _pairs(df.groupby("customer_segment")["revenue"].sum())},
    {"question": "Which state has the highest profit?", "kind": "label",
     "expected": lambda df: df.groupby("state")["profit"].sum().idxmax()},
    {"question": "What is the profit margin for each product category?", "kind": "pairs",
     "expected": _margin},
    {"question": "Which month had the highest revenue?", "kind": "label",
     "expected": lambda df: df.groupby(df["order_date"].dt.strftime("%Y-%m"))["revenue"].sum().idxmax()},
    {"question": "What is the total quantity sold in each product category?", "kind": "pairs",
     "expected": lambda df: _pairs(df.groupby("product_category")["quantity"].sum())},
]


# ---------------------------------------------------------------------------
# Comparing the system's answer with the expected answer
# ---------------------------------------------------------------------------

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def numbers_match(actual, expected: float) -> bool:
    """
    True if two numbers are the same within a small rounding difference.
    For rates only (small numbers), a fraction and its percentage also count
    as the same (0.3316 and 33.16), because both are correct ways to show a rate.
    """
    if not _is_number(actual):
        return False
    candidates = [expected]
    if abs(expected) <= 100:                           # looks like a rate, not money
        candidates += [expected * 100, expected / 100]
    for candidate in candidates:
        if abs(actual - candidate) <= max(0.006, abs(candidate) * 0.005):
            return True
    return False


def label_matches(cell, label: str) -> bool:
    """'West' == 'west'. '2025-10' matches the date '2025-10-01'. 2025 matches '2025'."""
    text, wanted = str(cell).strip().lower(), str(label).strip().lower()
    if text == wanted:
        return True
    if wanted[:4].isdigit():                           # a year or a year-month
        return text.startswith(wanted)
    return False


def is_correct(kind: str, expected, rows: list) -> bool:
    """Mark one answer. `rows` is the result table returned by the system."""
    if not rows:
        return False
    if kind == "number":
        return any(numbers_match(cell, float(expected)) for cell in rows[0])
    if kind == "label":
        return any(label_matches(cell, expected) for cell in rows[0])
    if kind in ("pairs", "ranked"):
        for position, (label, value) in enumerate(expected):
            # "ranked": the pair must be in this exact row. "pairs": it may be in any row.
            candidates = [rows[position]] if kind == "ranked" and position < len(rows) else \
                ([] if kind == "ranked" else rows)
            found = any(any(label_matches(cell, label) for cell in row) and
                        any(numbers_match(cell, value) for cell in row) for row in candidates)
            if not found:
                return False
        return True
    raise ValueError(f"Unknown kind: {kind}")
