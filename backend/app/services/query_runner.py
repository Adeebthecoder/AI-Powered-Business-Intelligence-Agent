"""
query_runner.py
---------------
Runs a query that has ALREADY passed sql_safety.check_and_fix_sql().

This is the second safety layer:
  - it logs in as the read-only database user, who has no permission to
    change anything and cannot see the users table
  - the transaction is marked READ ONLY
  - PostgreSQL cancels the query if it runs longer than the time limit
"""

from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.database import readonly_engine
from app.services.profiling import to_plain

settings = get_settings()


class QueryFailedError(Exception):
    """The database refused or could not finish the query."""

    def __init__(self, message: str, timed_out: bool = False):
        super().__init__(message)
        self.message = message
        self.timed_out = timed_out


def run_readonly_query(safe_sql: str) -> dict:
    """
    Run the query and return {"columns": [...], "rows": [[...], ...], "row_count": n}.
    Raises QueryFailedError with a short message if PostgreSQL reports an error.
    """
    timeout_ms = int(settings.sql_timeout_seconds * 1000)
    try:
        with readonly_engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")
            # exec_driver_sql sends the text as it is. (SQLAlchemy's text() would
            # treat ":name" inside the query as a parameter, which we do not want.)
            result = connection.exec_driver_sql(safe_sql)
            columns = list(result.keys())
            rows = [[to_plain(value) for value in row] for row in result.fetchall()]
            connection.rollback()               # nothing to save, we only read
    except DBAPIError as error:
        message = str(error.orig).strip().splitlines()[0] if error.orig else str(error)
        timed_out = "statement timeout" in message.lower()
        raise QueryFailedError(message, timed_out=timed_out)
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
