"""
loader.py
---------
Saves a clean table into PostgreSQL as its own table, and reads it back.

Every uploaded dataset gets one table inside the "dataset_tables" schema,
for example  dataset_tables.ds_3_indian_retail_sales
"""

import re

import pandas as pd
from sqlalchemy import Date, text

from app.config import DATASET_SCHEMA
from app.database import app_engine


def make_table_name(dataset_id: int, dataset_name: str) -> str:
    """Build a safe table name from the dataset id and name."""
    slug = re.sub(r"[^a-z0-9]+", "_", dataset_name.lower()).strip("_")[:30] or "data"
    return f"ds_{dataset_id}_{slug}"


def save_table(df: pd.DataFrame, table_name: str) -> None:
    """Write the clean table to PostgreSQL. Replaces the table if it exists."""
    # Columns that hold dates with no time of day are stored as DATE (not TIMESTAMP),
    # so results look like 2025-03-15 instead of 2025-03-15 00:00:00.
    sql_types = {}
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            values = df[column].dropna()
            if (values == values.dt.normalize()).all():
                sql_types[column] = Date()

    df.to_sql(table_name, app_engine, schema=DATASET_SCHEMA, if_exists="replace",
              index=False, chunksize=1000, method="multi", dtype=sql_types)


def load_table(table_name: str, schema_info: dict) -> pd.DataFrame:
    """Read a whole dataset table back into Pandas (used by forecast and evaluation)."""
    # Tell Pandas which columns are dates, using the schema saved at upload time.
    date_columns = [c["name"] for c in schema_info["columns"] if c["type"] == "date"]
    query = text(f'SELECT * FROM "{DATASET_SCHEMA}"."{table_name}"')
    with app_engine.connect() as connection:
        return pd.read_sql(query, connection, parse_dates=date_columns)


def drop_table(table_name: str) -> None:
    with app_engine.begin() as connection:
        connection.execute(text(f'DROP TABLE IF EXISTS "{DATASET_SCHEMA}"."{table_name}"'))
