"""
Tests for the small, pure helper parts of the AI flow:
  - reading JSON out of a messy LLM reply      (json_parsing.py)
  - checking the numbers in an insight         (insight.py)
  - choosing a chart from the result shape     (chart_selector.py)
  - "last quarter" measured from the data      (time_reference.py)
  - the forecast does not leak future data     (forecasting.py)
  - the mock LLM                               (mock_llm.py)

None of these need a database, an API key or a .env file.
"""

import numpy as np
import pandas as pd
import pytest

from app.services import forecasting, mock_llm
from app.services.chart_selector import choose_chart
from app.services.insight import format_number, numbers_are_grounded, template_insight
from app.services.json_parsing import extract_json
from app.services.time_reference import build_time_reference

REGION_ROWS = [["West", 24843883.05], ["South", 21830040.9], ["North", 21108958.8], ["East", 7784978.95]]


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reply", [
    '{"action": "sql", "sql": "SELECT 1"}',
    '```json\n{"action": "sql", "sql": "SELECT 1"}\n```',
    'Sure! Here is the query:\n{"action": "sql", "sql": "SELECT 1"}\nHope this helps.',
    '```\n{"action": "sql",\n "sql": "SELECT 1"}\n```\nNote: {this is not json}',
])
def test_json_is_found_in_messy_replies(reply):
    assert extract_json(reply) == {"action": "sql", "sql": "SELECT 1"}


def test_braces_inside_strings_do_not_confuse_the_parser():
    reply = '{"action": "clarify", "clarifying_question": "Do you mean {revenue} or {profit}?"}'
    assert extract_json(reply)["clarifying_question"] == "Do you mean {revenue} or {profit}?"


@pytest.mark.parametrize("reply", ["", "I cannot answer that.", "{broken json", "[1, 2, 3]"])
def test_no_json_returns_none(reply):
    assert extract_json(reply) is None


# ---------------------------------------------------------------------------
# Insight number check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("insight", [
    "West leads with revenue of 24843883.05, while East is last at 7784978.95.",
    "West leads with 24,843,883 and East trails at 7,784,979.",               # rounded, with commas
    "West leads with 2,48,43,883 and East trails at 77,84,979.",              # Indian digit grouping
    "West made about 2.48 crore while East made 77.85 lakh.",                  # lakh and crore
    "West made 24.8 million. All 4 regions are shown.",                        # million, and a row count
    "West is the strongest region and East is the weakest.",                   # no numbers at all
])
def test_grounded_insights_pass(insight):
    ok, unsupported = numbers_are_grounded(insight, REGION_ROWS, "Show revenue by region")
    assert ok, unsupported


@pytest.mark.parametrize("insight", [
    "West leads with revenue of 30,000,000.",                                  # invented number
    "West earned 17,058,904 more than East.",                                  # a difference the LLM calculated
    "West made 3.2 times as much as East.",                                    # a ratio the LLM calculated
    "West holds 32.9% of total revenue.",                                      # a percentage the LLM calculated
    "Revenue grew strongly in 2025.",                                          # a year that is not in the result
])
def test_invented_numbers_are_caught(insight):
    ok, unsupported = numbers_are_grounded(insight, REGION_ROWS, "Show revenue by region")
    assert not ok
    assert unsupported


def test_numbers_from_the_question_are_allowed():
    rows = [["Laptop", 500.0], ["Phone", 300.0]]
    ok, _ = numbers_are_grounded("Of the top 5 products in 2025, Laptop leads with 500.",
                                 rows, "What are the top 5 products in 2025?")
    assert ok


def test_fraction_may_be_written_as_percentage():
    ok, _ = numbers_are_grounded("Furniture has an average discount of 33.16%.", [["Furniture", 0.3316]])
    assert ok


def test_product_names_with_digits_are_not_treated_as_numbers():
    rows = [["Smartphone 5G 128GB", 1000.0]]
    ok, _ = numbers_are_grounded("Smartphone 5G 128GB sold 1,000.", rows)
    assert ok


def test_template_insight_passes_its_own_check():
    chart = choose_chart(["region", "total_revenue"], REGION_ROWS, "Show revenue by region")
    text = template_insight(["region", "total_revenue"], REGION_ROWS, chart)
    assert "West" in text and "East" in text
    assert numbers_are_grounded(text, REGION_ROWS)[0]


def test_indian_number_format():
    assert format_number(75567862.25) == "7,55,67,862.25"
    assert format_number(-423697.68) == "-4,23,697.68"
    assert format_number(999) == "999"


# ---------------------------------------------------------------------------
# Chart selection
# ---------------------------------------------------------------------------

def test_single_value_gives_kpi():
    assert choose_chart(["total_revenue"], [[75567862.25]])["type"] == "kpi"


def test_category_and_number_gives_bar():
    assert choose_chart(["region", "total_revenue"], REGION_ROWS)["type"] == "bar"


def test_time_column_gives_line():
    rows = [["2025-01-01", 10.0], ["2025-02-01", 12.0], ["2025-03-01", 15.0]]
    assert choose_chart(["month", "revenue"], rows)["type"] == "line"


def test_year_number_column_is_a_time_axis():
    rows = [[2023, 10.0], [2024, 12.0], [2025, 15.0]]
    chart = choose_chart(["year", "revenue"], rows)
    assert chart["type"] == "line" and chart["x"] == ["2023", "2024", "2025"]


def test_ranked_months_give_bars_not_a_line():
    rows = [["2025-10-01", 43.0], ["2024-11-01", 32.0], ["2024-10-01", 31.0]]      # ordered by value, not time
    assert choose_chart(["month", "revenue"], rows)["type"] == "bar"


def test_share_question_gives_pie():
    chart = choose_chart(["region", "total_revenue"], REGION_ROWS, "What is the share of revenue by region?")
    assert chart["type"] == "pie"


def test_two_categories_give_grouped_bars():
    rows = [["North", "Consumer", 5.0], ["North", "Corporate", 3.0],
            ["South", "Consumer", 6.0], ["South", "Corporate", 2.0]]
    chart = choose_chart(["region", "segment", "revenue"], rows)
    assert chart["type"] == "bar" and len(chart["series"]) == 2


def test_only_numbers_give_scatter():
    rows = [[0.1 * i, 100.0 - i] for i in range(10)]
    assert choose_chart(["discount", "profit"], rows)["type"] == "scatter"


def test_empty_result_gives_table():
    assert choose_chart(["region"], [])["type"] == "table"


# ---------------------------------------------------------------------------
# Time reference
# ---------------------------------------------------------------------------

def schema_with_dates(first, last):
    return {"columns": [{"name": "order_date", "type": "date", "min": first, "max": last}]}


def test_last_quarter_when_data_ends_on_a_quarter_end():
    reference = build_time_reference(schema_with_dates("2023-01-01", "2025-12-31"))
    assert (reference["last_quarter_start"], reference["last_quarter_end"]) == ("2025-10-01", "2025-12-31")
    assert reference["last_quarter_name"] == "Q4 2025"


def test_last_quarter_when_newest_quarter_is_unfinished():
    reference = build_time_reference(schema_with_dates("2023-01-01", "2025-11-20"))
    assert (reference["last_quarter_start"], reference["last_quarter_end"]) == ("2025-07-01", "2025-09-30")
    assert (reference["last_month_start"], reference["last_month_end"]) == ("2025-10-01", "2025-10-31")


def test_no_date_column_gives_no_reference():
    assert build_time_reference({"columns": [{"name": "region", "type": "text"}]}) is None


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def make_series(months=36):
    """A made-up monthly series with a trend and a yearly pattern."""
    index = pd.date_range("2023-01-01", periods=months, freq="MS")
    values = 100 + 2 * np.arange(months) + 30 * (index.month.isin([10, 11]))
    return pd.Series(values.astype(float), index=index)


def test_forecast_compares_models_and_picks_lowest_rmse():
    result = forecasting.run_forecast(make_series())
    assert len(result["scores"]) >= 2
    assert all(score["mae"] >= 0 and score["rmse"] >= 0 for score in result["scores"])
    assert result["best_model"] == min(result["scores"], key=lambda s: s["rmse"])["model"]
    assert len(result["forecast"]) == 3
    assert result["forecast"][0]["month"] == "2026-01-01"       # the month after the data ends


def test_forecast_does_not_leak_test_data_into_training():
    """
    Change ONLY the held-out test months. If the models were trained without
    seeing them, their predictions for those months must stay exactly the same.
    """
    original = make_series()
    tampered = original.copy()
    tampered.iloc[-6:] = 999999.0                               # the test period is the last 6 months
    first = forecasting.run_forecast(original)["test"]["predictions"]
    second = forecasting.run_forecast(tampered)["test"]["predictions"]
    assert first == second


def test_forecast_needs_enough_history():
    with pytest.raises(forecasting.ForecastError):
        forecasting.run_forecast(make_series(months=8))


def test_unfinished_last_month_is_left_out():
    dates = pd.date_range("2024-01-01", "2025-03-10", freq="D")        # March 2025 stops on day 10
    table = pd.DataFrame({"d": dates, "v": 1.0})
    series = forecasting.monthly_series(table, "d", "v")
    assert series.index[-1] == pd.Timestamp("2025-02-01")


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

SAMPLE_COLUMNS = sorted(mock_llm.REQUIRED_COLUMNS | {"sub_category", "unit_price", "cost"})
TIME = build_time_reference(schema_with_dates("2023-01-01", "2025-12-31"))


def test_mock_answers_a_known_question_with_sql():
    reply = extract_json(mock_llm.mock_sql_reply("What is the total revenue?", "t", SAMPLE_COLUMNS, TIME))
    assert reply["action"] == "sql" and "SUM(revenue)" in reply["sql"]


def test_mock_tolerates_small_typing_differences():
    reply = extract_json(mock_llm.mock_sql_reply("whats the total revenue", "t", SAMPLE_COLUMNS, TIME))
    assert reply["action"] == "sql"


def test_mock_asks_for_clarification_when_unclear():
    reply = extract_json(mock_llm.mock_sql_reply("Show me the best one", "t", SAMPLE_COLUMNS, TIME))
    assert reply["action"] == "clarify"


def test_mock_does_not_guess_unknown_questions():
    reply = extract_json(mock_llm.mock_sql_reply("Who will win the cricket match?", "t", SAMPLE_COLUMNS, TIME))
    assert reply["action"] == "clarify"
