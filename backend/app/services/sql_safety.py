"""
sql_safety.py
-------------
The safety gate for SQL written by the LLM. NOTHING the LLM writes reaches the
database without passing through check_and_fix_sql() first.

We do not search the text for bad words (that is easy to trick). Instead the
query is parsed into a tree with the sqlglot library and the tree is inspected.

A query is allowed only if ALL of these are true:
  1. It is exactly one statement.
  2. That statement is a SELECT (a WITH ... SELECT is fine too).
  3. Nothing inside it changes data (no INSERT, UPDATE, DELETE, DROP ...).
  4. It reads only the user's own dataset table.
  5. Every column it mentions exists in that table.
  6. It only calls functions from a known safe list.
After that, a row limit is added (or lowered) automatically.

This is the first layer. The second layer is in query_runner.py: the query is
run by a read-only database user with a time limit.

This file has no database code, so it is easy to test (tests/test_sql_safety.py).
"""

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# sqlglot prints a warning for statements it does not fully understand (for
# example VACUUM). We block those anyway, so the warning is just noise.
logging.getLogger("sqlglot").setLevel(logging.ERROR)


class UnsafeQueryError(Exception):
    """
    Raised when a query is not allowed.

    retryable = True   the LLM made an honest mistake (for example a wrong
                       column name), so it is worth asking it once more.
    retryable = False  the query tried something that is never allowed
                       (for example DELETE). It is blocked at once.
    """

    def __init__(self, reason: str, retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


# Statement types that change data or settings. If any of these appears
# anywhere in the tree, the query is blocked.
FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in (
        "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
        "TruncateTable", "Command", "Copy", "Set", "Grant", "Revoke", "Transaction",
        "Commit", "Rollback", "Use", "Pragma", "Into", "Lock", "Analyze", "Comment",
        "Describe", "Kill", "LoadData", "Execute",
    ) if hasattr(exp, name)          # some names differ between sqlglot versions
)

# Functions sqlglot does not know by name are only allowed if listed here.
# Anything else (pg_sleep, pg_read_file, dblink, set_config ...) is blocked.
SAFE_EXTRA_FUNCTIONS = {
    "to_char", "to_date", "date_part", "age", "make_date", "date",
    "trunc", "div", "mod", "abs", "ceil", "ceiling", "floor", "sign", "power", "sqrt", "ln", "log", "exp",
    "round", "greatest", "least", "nullif", "coalesce",
    "initcap", "upper", "lower", "length", "concat", "concat_ws", "split_part", "left", "right",
    "btrim", "ltrim", "rtrim", "trim", "replace", "strpos", "substr", "substring", "lpad", "rpad",
    "string_agg", "array_agg", "percentile_cont", "percentile_disc", "mode", "width_bucket",
    "corr", "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop",
    "row_number", "rank", "dense_rank", "ntile", "lag", "lead", "first_value", "last_value",
    "sum", "avg", "min", "max", "count",
}


def check_and_fix_sql(sql: str, table_name: str, columns: list[str], schema: str, max_rows: int) -> str:
    """
    Check one SQL query and return a safe version of it.

    sql         the query the LLM wrote
    table_name  the only table the query may read
    columns     the column names of that table
    schema      the PostgreSQL schema the table lives in
    max_rows    the largest number of rows the query may return

    Raises UnsafeQueryError if the query is not allowed.
    """
    cleaned = (sql or "").strip()
    while cleaned.endswith(";"):                     # one trailing semicolon is harmless
        cleaned = cleaned[:-1].strip()
    if not cleaned:
        raise UnsafeQueryError("The query is empty.", retryable=True)

    # ---- Rule 1: parse it, and insist on exactly one statement ---------------
    try:
        statements = [s for s in sqlglot.parse(cleaned, read="postgres") if s is not None]
    except SqlglotError as error:
        raise UnsafeQueryError(f"The query is not valid SQL: {str(error).splitlines()[0]}", retryable=True)
    if len(statements) != 1:
        raise UnsafeQueryError("Only one SQL statement is allowed.")
    tree = statements[0]

    # ---- Rule 2: it must be a SELECT -------------------------------------------
    if not isinstance(tree, exp.Select):
        raise UnsafeQueryError(f"Only SELECT queries are allowed (found {tree.key.upper()}).")

    # ---- Rule 3: nothing inside may change data ------------------------------
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeQueryError(f"The query contains a forbidden operation: {node.key.upper()}.")
    if tree.args.get("locks"):
        raise UnsafeQueryError("Row locking (FOR UPDATE) is not allowed.")

    # Names defined inside the query itself: WITH names and "AS" names.
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    alias_names = {alias.alias.lower() for alias in tree.find_all(exp.Alias) if alias.alias}
    for table_alias in tree.find_all(exp.TableAlias):
        alias_names.update(c.name.lower() for c in table_alias.columns)

    # ---- Rule 4: only the user's own table -----------------------------------
    reads_dataset = False
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeQueryError("Table functions are not allowed.")
        name = table.name.lower()
        if name in cte_names and not table.db:
            continue                                  # a WITH name defined in this query
        if name != table_name.lower() or table.catalog or (table.db and table.db.lower() != schema.lower()):
            raise UnsafeQueryError(f"The query reads a table that is not allowed: {table.sql()}.")
        # Always point at the right schema, so there is no doubt which table is read.
        table.set("db", exp.to_identifier(schema, quoted=True))
        table.set("this", exp.to_identifier(table_name, quoted=True))
        reads_dataset = True
    if not reads_dataset:
        # Stops things like SELECT version() that ask about the server, not the data.
        raise UnsafeQueryError(f"The query must read the dataset table '{table_name}'.", retryable=True)

    # ---- Rule 5: only columns that exist -------------------------------------
    known = {c.lower() for c in columns} | alias_names
    for column in tree.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue                                  # table.* is fine
        if column.name.lower() not in known:
            raise UnsafeQueryError(
                f"Unknown column '{column.name}'. Available columns: {', '.join(columns)}.",
                retryable=True)

    # ---- Rule 6: only safe functions -----------------------------------------
    for function in tree.find_all(exp.Anonymous):
        name = str(function.this).lower()
        if name not in SAFE_EXTRA_FUNCTIONS:
            raise UnsafeQueryError(f"The function '{name}' is not allowed.",
                                   retryable=not name.startswith(("pg_", "lo_", "dblink", "set_")))

    # ---- Row limit: add one, or lower one that is too high -------------------
    if tree.args.get("fetch"):
        raise UnsafeQueryError("Use LIMIT instead of FETCH FIRST.", retryable=True)
    limit = tree.args.get("limit")
    current = None
    if limit is not None and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        current = int(limit.expression.name)
    if current is None or current > max_rows:
        tree = tree.limit(max_rows)

    return tree.sql(dialect="postgres")
