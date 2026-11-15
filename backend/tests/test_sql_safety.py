"""
Tests for the SQL safety checker (app/services/sql_safety.py).

These tests need no database and no .env file. Run them from the backend folder:
    pytest
"""

import pytest

from app.services.sql_safety import UnsafeQueryError, check_and_fix_sql

TABLE = "ds_1_sales"
SCHEMA = "dataset_tables"
COLUMNS = ["order_id", "order_date", "customer_id", "region", "product_category",
           "quantity", "discount", "revenue", "profit"]
MAX_ROWS = 1000


def check(sql: str) -> str:
    return check_and_fix_sql(sql, TABLE, COLUMNS, SCHEMA, MAX_ROWS)


# ---------------------------------------------------------------------------
# Queries that must be ALLOWED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT region, SUM(revenue) AS total_revenue FROM ds_1_sales GROUP BY region",
    "SELECT COUNT(*) AS orders FROM ds_1_sales WHERE region = 'East'",
    "SELECT COUNT(DISTINCT customer_id) AS customers FROM ds_1_sales",
    "SELECT date_trunc('month', order_date)::date AS month, SUM(revenue) AS revenue "
    "FROM ds_1_sales GROUP BY month ORDER BY month",
    "SELECT EXTRACT(YEAR FROM order_date)::int AS year, ROUND(SUM(profit)::numeric, 2) AS profit "
    "FROM ds_1_sales GROUP BY year",
    "SELECT to_char(order_date, 'YYYY-MM') AS month, AVG(discount) AS avg_discount FROM ds_1_sales GROUP BY 1",
    "WITH totals AS (SELECT region, SUM(revenue) AS r FROM ds_1_sales GROUP BY region) "
    "SELECT region, r FROM totals ORDER BY r DESC",
    "SELECT s.region FROM ds_1_sales AS s WHERE s.revenue > (SELECT AVG(revenue) FROM ds_1_sales)",
    "SELECT region, RANK() OVER (ORDER BY SUM(revenue) DESC) AS position FROM ds_1_sales GROUP BY region",
    "SELECT CASE WHEN profit < 0 THEN 'loss' ELSE 'gain' END AS result, COUNT(*) AS n FROM ds_1_sales GROUP BY 1",
    "SELECT * FROM dataset_tables.ds_1_sales",
    "select region from DS_1_SALES;",                       # capitals and one trailing semicolon are fine
])
def test_safe_queries_are_allowed(sql):
    safe = check(sql)
    assert safe.upper().startswith(("SELECT", "WITH"))


# ---------------------------------------------------------------------------
# Queries that must be BLOCKED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    # statements that change data or structure
    "DELETE FROM ds_1_sales",
    "DELETE FROM ds_1_sales WHERE region = 'East'",
    "UPDATE ds_1_sales SET revenue = 0",
    "INSERT INTO ds_1_sales (region) VALUES ('X')",
    "DROP TABLE ds_1_sales",
    "TRUNCATE ds_1_sales",
    "ALTER TABLE ds_1_sales ADD COLUMN x int",
    "CREATE TABLE copy AS SELECT * FROM ds_1_sales",
    "GRANT ALL ON ds_1_sales TO PUBLIC",
    "COPY ds_1_sales TO '/tmp/out.csv'",
    "SET statement_timeout = 0",
    "VACUUM",
    # more than one statement
    "SELECT * FROM ds_1_sales; DROP TABLE ds_1_sales",
    "SELECT 1; SELECT 2",
    # a harmful statement hidden inside a SELECT
    "WITH gone AS (DELETE FROM ds_1_sales RETURNING *) SELECT * FROM gone",
    "SELECT * INTO new_table FROM ds_1_sales",
    "SELECT * FROM ds_1_sales FOR UPDATE",
    # other tables
    "SELECT * FROM users",
    "SELECT * FROM public.users",
    "SELECT * FROM ds_2_other_users_data",
    "SELECT * FROM ds_1_sales, users",
    "SELECT * FROM ds_1_sales JOIN users ON true",
    "SELECT (SELECT password_hash FROM users LIMIT 1) AS stolen FROM ds_1_sales",
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM other_schema.ds_1_sales",
    "SELECT * FROM generate_series(1, 100000000)",
    # dangerous functions
    "SELECT pg_sleep(60) FROM ds_1_sales",
    "SELECT pg_read_file('/etc/passwd') FROM ds_1_sales",
    "SELECT lo_import('/etc/passwd') FROM ds_1_sales",
    "SELECT set_config('statement_timeout', '0', false) FROM ds_1_sales",
    "SELECT dblink('host=evil', 'select 1') FROM ds_1_sales",
    "SELECT query_to_xml('select * from users', true, true, '') FROM ds_1_sales",
    # questions about the server instead of the data
    "SELECT version()",
    "SELECT current_user",
    # not SQL at all
    "",
    "please show me everything",
    # UNION is not needed for our questions, so it is not allowed
    "SELECT region FROM ds_1_sales UNION SELECT email FROM users",
])
def test_unsafe_queries_are_blocked(sql):
    with pytest.raises(UnsafeQueryError):
        check(sql)


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def test_unknown_column_is_blocked_and_can_be_retried():
    with pytest.raises(UnsafeQueryError) as error:
        check("SELECT salary FROM ds_1_sales")
    assert "salary" in error.value.reason
    assert error.value.retryable is True        # an honest mistake, the LLM gets one more try


def test_destructive_query_is_not_retried():
    with pytest.raises(UnsafeQueryError) as error:
        check("DELETE FROM ds_1_sales")
    assert error.value.retryable is False       # blocked at once, no second chance


def test_alias_names_are_accepted_as_columns():
    safe = check("SELECT region, SUM(revenue) AS total FROM ds_1_sales GROUP BY region ORDER BY total DESC")
    assert "total" in safe


# ---------------------------------------------------------------------------
# Row limit
# ---------------------------------------------------------------------------

def test_limit_is_added_when_missing():
    assert check("SELECT * FROM ds_1_sales").endswith(f"LIMIT {MAX_ROWS}")


def test_limit_that_is_too_high_is_lowered():
    assert check("SELECT * FROM ds_1_sales LIMIT 999999").endswith(f"LIMIT {MAX_ROWS}")


def test_small_limit_is_kept():
    assert check("SELECT * FROM ds_1_sales LIMIT 5").endswith("LIMIT 5")


def test_limit_all_is_replaced():
    assert check("SELECT * FROM ds_1_sales LIMIT ALL").endswith(f"LIMIT {MAX_ROWS}")


# ---------------------------------------------------------------------------
# The table is always pinned to the right schema
# ---------------------------------------------------------------------------

def test_table_is_qualified_with_the_dataset_schema():
    safe = check("SELECT region FROM ds_1_sales")
    assert '"dataset_tables"."ds_1_sales"' in safe
