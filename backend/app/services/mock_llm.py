"""
mock_llm.py
-----------
A stand-in for the LLM, used when LLM_MODE=mock in the .env file.

It answers a FIXED list of questions about the sample retail dataset without
any API call. Use it to:
  - test the whole app with no API key and no internet
  - keep the live demo safe if OpenRouter is down or the daily limit is used up

How it stays honest: the mock returns its answer as a JSON reply inside a
code fence, exactly like a real model often does. That reply then goes through
the SAME steps as a live reply: JSON parsing, the SQL safety check, the
read-only database user, chart selection and history. Only the "thinking" is
faked. The numbers always come from really running the SQL.

One mock question is a trap on purpose ("Delete all orders from the East
region"): the mock replies with a DELETE statement so you can show the safety
checker blocking it.
"""

import difflib
import json
import re

# The mock only understands the sample dataset, which has these columns.
REQUIRED_COLUMNS = {"order_id", "order_date", "customer_id", "customer_segment", "region", "state",
                    "city", "product_category", "product_name", "quantity", "discount", "revenue",
                    "profit", "payment_mode"}

# question -> SQL. {table} and the {last_quarter_...} parts are filled in at run time.
MOCK_SQL = {
    # ----- single numbers -----
    "What is the total revenue?":
        "SELECT ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table}",
    "What is the total profit?":
        "SELECT ROUND(SUM(profit)::numeric, 2) AS total_profit FROM {table}",
    "How many orders are there?":
        "SELECT COUNT(*) AS total_orders FROM {table}",
    "What is the average order value?":
        "SELECT ROUND(AVG(revenue)::numeric, 2) AS average_order_value FROM {table}",
    "How many unique customers are there?":
        "SELECT COUNT(DISTINCT customer_id) AS unique_customers FROM {table}",

    # ----- regions -----
    "Which region had the highest revenue last quarter?":
        "SELECT region, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "WHERE order_date >= '{last_quarter_start}' AND order_date <= '{last_quarter_end}' "
        "GROUP BY region ORDER BY total_revenue DESC",
    "Show total revenue by region":
        "SELECT region, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY region ORDER BY total_revenue DESC",
    "Show revenue by region and year":
        "SELECT region, EXTRACT(YEAR FROM order_date)::int AS year, "
        "ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY region, year ORDER BY region, year",
    "Which state has the highest profit?":
        "SELECT state, ROUND(SUM(profit)::numeric, 2) AS total_profit FROM {table} "
        "GROUP BY state ORDER BY total_profit DESC LIMIT 10",
    "What are the top 5 cities by revenue?":
        "SELECT city, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY city ORDER BY total_revenue DESC LIMIT 5",

    # ----- categories and products -----
    "Which product category has the highest revenue?":
        "SELECT product_category, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY product_category ORDER BY total_revenue DESC",
    "Which product category has the lowest profit?":
        "SELECT product_category, ROUND(SUM(profit)::numeric, 2) AS total_profit FROM {table} "
        "GROUP BY product_category ORDER BY total_profit ASC",
    "Compare revenue and profit by product category":
        "SELECT product_category, ROUND(SUM(revenue)::numeric, 2) AS total_revenue, "
        "ROUND(SUM(profit)::numeric, 2) AS total_profit FROM {table} "
        "GROUP BY product_category ORDER BY total_revenue DESC",
    "What is the average discount for each product category?":
        "SELECT product_category, ROUND(AVG(discount)::numeric, 4) AS average_discount FROM {table} "
        "GROUP BY product_category ORDER BY average_discount DESC",
    "What is the profit margin for each product category?":
        "SELECT product_category, ROUND((SUM(profit) / SUM(revenue) * 100)::numeric, 2) AS profit_margin_percent "
        "FROM {table} GROUP BY product_category ORDER BY profit_margin_percent DESC",
    "What is the total quantity sold in each product category?":
        "SELECT product_category, SUM(quantity) AS total_quantity FROM {table} "
        "GROUP BY product_category ORDER BY total_quantity DESC",
    "What are the top 5 products by revenue?":
        "SELECT product_name, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY product_name ORDER BY total_revenue DESC LIMIT 5",
    "Which region generated the highest revenue last quarter, and what products contributed most?":
        "WITH top_region AS (SELECT region FROM {table} "
        "WHERE order_date >= '{last_quarter_start}' AND order_date <= '{last_quarter_end}' "
        "GROUP BY region ORDER BY SUM(revenue) DESC LIMIT 1) "
        "SELECT region, product_name, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "WHERE order_date >= '{last_quarter_start}' AND order_date <= '{last_quarter_end}' "
        "AND region = (SELECT region FROM top_region) "
        "GROUP BY region, product_name ORDER BY total_revenue DESC LIMIT 5",

    # ----- time -----
    "Show the monthly revenue trend":
        "SELECT date_trunc('month', order_date)::date AS month, ROUND(SUM(revenue)::numeric, 2) AS total_revenue "
        "FROM {table} GROUP BY month ORDER BY month",
    "Show monthly revenue for 2025":
        "SELECT date_trunc('month', order_date)::date AS month, ROUND(SUM(revenue)::numeric, 2) AS total_revenue "
        "FROM {table} WHERE order_date >= '2025-01-01' AND order_date <= '2025-12-31' "
        "GROUP BY month ORDER BY month",
    "Show total revenue by year":
        "SELECT EXTRACT(YEAR FROM order_date)::int AS year, ROUND(SUM(revenue)::numeric, 2) AS total_revenue "
        "FROM {table} GROUP BY year ORDER BY year",
    "Which month had the highest revenue?":
        "SELECT date_trunc('month', order_date)::date AS month, ROUND(SUM(revenue)::numeric, 2) AS total_revenue "
        "FROM {table} GROUP BY month ORDER BY total_revenue DESC LIMIT 5",

    # ----- customers and payments -----
    "Show revenue by customer segment":
        "SELECT customer_segment, ROUND(SUM(revenue)::numeric, 2) AS total_revenue FROM {table} "
        "GROUP BY customer_segment ORDER BY total_revenue DESC",
    "Which payment mode is used the most?":
        "SELECT payment_mode, COUNT(*) AS total_orders FROM {table} "
        "GROUP BY payment_mode ORDER BY total_orders DESC",
    "What is the share of orders by payment mode?":
        "SELECT payment_mode, COUNT(*) AS total_orders FROM {table} "
        "GROUP BY payment_mode ORDER BY total_orders DESC",

    # ----- the trap: shows the safety checker blocking a harmful query -----
    "Delete all orders from the East region":
        "DELETE FROM {table} WHERE region = 'East'",
}

# Unclear questions -> the clarifying question the system asks back.
MOCK_CLARIFY = {
    "Show me the best one":
        "Best what, and by which measure? For example: best region by revenue, "
        "or best product category by profit.",
    "How are we doing?":
        "Which number would you like to look at: revenue, profit or number of orders? "
        "And for which period?",
    "Show me the sales":
        "How would you like sales broken down: by region, by product category, or by month?",
}


def normalise(question: str) -> str:
    """'  Which REGION had... ?' -> 'which region had'. Used to compare questions."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", question.lower())).strip()


_SQL_BY_KEY = {normalise(q): sql for q, sql in MOCK_SQL.items()}
_CLARIFY_BY_KEY = {normalise(q): text for q, text in MOCK_CLARIFY.items()}


def supported_questions() -> list[str]:
    """The questions the mock can answer (shown as suggestions on the Ask page)."""
    return list(MOCK_SQL)


def mock_sql_reply(question: str, table_name: str, columns: list[str], time_reference: dict | None) -> str:
    """
    Return what a real model would return for call 1: a JSON reply as text.
    Small typing differences are tolerated ("whats the total revenue").
    """
    if not REQUIRED_COLUMNS.issubset(set(columns)):
        return _fenced({"action": "clarify", "clarifying_question":
                        "Mock mode only knows the sample retail dataset (indian_retail_sales.csv). "
                        "For your own files, set LLM_MODE=live in the .env file."})

    key = normalise(question)
    if key in _CLARIFY_BY_KEY:
        return _fenced({"action": "clarify", "clarifying_question": _CLARIFY_BY_KEY[key]})

    if key not in _SQL_BY_KEY:
        close = difflib.get_close_matches(key, list(_SQL_BY_KEY), n=1, cutoff=0.86)
        key = close[0] if close else None
    if key is None:
        return _fenced({"action": "clarify", "clarifying_question":
                        "Mock mode can only answer its fixed list of demo questions. "
                        "Pick one of the suggested questions, or set LLM_MODE=live to ask anything."})

    sql = _SQL_BY_KEY[key].format(table=table_name, **(time_reference or {}))
    return _fenced({"action": "sql", "sql": sql})


def _fenced(reply: dict) -> str:
    """Wrap the JSON in a code fence with a sentence in front, like real models often do,
    so that mock mode also exercises the defensive JSON parser."""
    return "Here is the answer:\n```json\n" + json.dumps(reply) + "\n```"
