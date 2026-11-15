"""
Tests for the data cleaning pipeline (app/services/cleaning.py).

These tests need no database and no .env file. Run them from the backend folder:
    pytest
"""

from pathlib import Path

import pandas as pd
import pytest

from app.services.cleaning import clean_column_name, clean_dataframe, parse_dates, read_uploaded_file

SAMPLE_CSV = Path(__file__).resolve().parents[2] / "data" / "indian_retail_sales.csv"


def messy_table() -> pd.DataFrame:
    """A tiny table with every kind of mess the pipeline should fix."""
    return pd.DataFrame({
        "Order ID": ["A1", "A2", "A3", "A3", "A4", "A5"],
        "Order Date": ["2024-01-15", "16/01/2024", "17-Jan-2024", "17-Jan-2024", "2024-01-18", "2024-01-19"],
        " Region ": ["North", "north", "North", "North", " South ", "South"],
        "Unit Price (INR)": ["1,000", "2000", "1500", "1500", "", "3000"],
        "Segment": ["Consumer", "", "Corporate", "Corporate", "Consumer", "NA"],
    })


def step(summary: dict, name: str) -> dict:
    return next(s for s in summary["steps"] if s["step"] == name)


# ---------------------------------------------------------------------------
# Column names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Order Date", "order_date"),
    ("  Unit Price (INR) ", "unit_price_inr"),
    ("customerSegment", "customer_segment"),
    ("2024 Sales", "col_2024_sales"),          # a name cannot start with a digit
    ("order", "order_col"),                    # "order" is an SQL keyword
    ("%%%", "column"),
])
def test_clean_column_name(raw, expected):
    assert clean_column_name(raw) == expected


def test_duplicate_column_names_are_made_unique():
    table = pd.DataFrame([[1, 2]], columns=["Sales", "sales"])
    clean, _ = clean_dataframe(table)
    assert list(clean.columns) == ["sales", "sales_2"]


# ---------------------------------------------------------------------------
# The whole pipeline on the small messy table
# ---------------------------------------------------------------------------

def test_column_names_are_cleaned():
    clean, summary = clean_dataframe(messy_table())
    assert list(clean.columns) == ["order_id", "order_date", "region", "unit_price_inr", "segment"]
    assert summary["renamed_columns"]["Unit Price (INR)"] == "unit_price_inr"


def test_duplicate_rows_are_removed():
    clean, summary = clean_dataframe(messy_table())
    assert len(clean) == 5
    assert step(summary, "Remove duplicate rows")["rows_affected"] == 1
    assert summary["rows_before"] == 6 and summary["rows_after"] == 5


def test_mixed_date_formats_become_real_dates():
    clean, summary = clean_dataframe(messy_table())
    assert pd.api.types.is_datetime64_any_dtype(clean["order_date"])
    assert list(clean["order_date"].dt.strftime("%Y-%m-%d")) == [
        "2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19"]
    assert step(summary, "Standardise date formats")["rows_affected"] == 3


def test_ambiguous_dates_are_read_day_first():
    # 03/04/2024 is 3 April in India, not 4 March.
    parsed = parse_dates(pd.Series(["03/04/2024"], dtype="string"))
    assert parsed.iloc[0] == pd.Timestamp(2024, 4, 3)


def test_numbers_stored_as_text_become_numbers():
    clean, _ = clean_dataframe(messy_table())
    assert pd.api.types.is_numeric_dtype(clean["unit_price_inr"])
    assert 1000 in clean["unit_price_inr"].tolist()       # "1,000" was read correctly


def test_capital_letters_are_made_consistent():
    clean, summary = clean_dataframe(messy_table())
    assert set(clean["region"]) == {"North", "South"}     # no "north", "NORTH" or " South "
    assert step(summary, "Fix inconsistent capital letters")["rows_affected"] == 1


def test_missing_values_are_filled():
    clean, summary = clean_dataframe(messy_table())
    assert clean.isna().sum().sum() == 0
    assert "Unknown" in clean["segment"].tolist()          # missing text -> "Unknown"
    # missing number -> median of the other prices (1000, 2000, 1500, 3000 -> 1750)
    assert 1750 in clean["unit_price_inr"].tolist()
    assert summary["missing_before"]["segment"] == 2       # "" and "NA" both count as missing


def test_empty_rows_and_columns_are_dropped():
    table = pd.DataFrame({"a": ["1", "", "3"], "b": ["x", "", "z"], "empty": ["", "", ""]})
    clean, _ = clean_dataframe(table)
    assert list(clean.columns) == ["a", "b"]
    assert len(clean) == 2


def test_cleaning_is_reproducible():
    first, _ = clean_dataframe(messy_table())
    second, _ = clean_dataframe(messy_table())
    pd.testing.assert_frame_equal(first, second)


def test_clean_table_is_not_changed_by_cleaning_again():
    once, _ = clean_dataframe(messy_table())
    twice, summary = clean_dataframe(once)
    assert len(twice) == len(once)
    assert step(summary, "Remove duplicate rows")["rows_affected"] == 0


# ---------------------------------------------------------------------------
# The real sample dataset
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample():
    return clean_dataframe(read_uploaded_file(str(SAMPLE_CSV), SAMPLE_CSV.name))


def test_sample_dataset_duplicates_removed(sample):
    clean, summary = sample
    assert summary["rows_before"] > summary["rows_after"]
    assert clean["order_id"].is_unique                     # one row per order


def test_sample_dataset_types(sample):
    clean, _ = sample
    assert pd.api.types.is_datetime64_any_dtype(clean["order_date"])
    for column in ["quantity", "unit_price", "discount", "revenue", "cost", "profit"]:
        assert pd.api.types.is_numeric_dtype(clean[column]), column


def test_sample_dataset_has_clean_categories(sample):
    clean, _ = sample
    assert set(clean["region"]) == {"North", "South", "East", "West"}
    assert clean["product_category"].nunique() == 6


def test_sample_dataset_has_no_missing_values_left(sample):
    clean, _ = sample
    assert clean.isna().sum().sum() == 0


def test_sample_dataset_dates_are_in_range(sample):
    clean, _ = sample
    assert clean["order_date"].min() >= pd.Timestamp(2023, 1, 1)
    assert clean["order_date"].max() <= pd.Timestamp(2025, 12, 31)
