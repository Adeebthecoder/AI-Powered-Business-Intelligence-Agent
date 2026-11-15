"""
cleaning.py
-----------
The data cleaning pipeline. It takes the raw table read from a CSV or Excel
file and returns a clean table plus a summary of everything it changed.

The steps always run in the same order, so the same file always gives the
same result (reproducible):

  1. Clean column names        "Order Date " -> "order_date"
  2. Tidy text                 trim spaces, treat "", "NA", "null" as missing
  3. Remove empty rows/columns
  4. Fix data types            numbers stored as text -> numbers,
                               dates in mixed formats -> real dates
  5. Fix capital letters       "north", "NORTH" -> "North"
  6. Remove duplicate rows
  7. Fill missing values       numbers -> median, text -> "Unknown"

This file uses only Pandas. It does not touch the database, so it is easy to
test (see tests/test_cleaning.py).
"""

import re

import pandas as pd

# Text values that really mean "no value".
MISSING_WORDS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "?"}

# Column names that would clash with SQL keywords. We add "_col" to them.
SQL_RESERVED = {"order", "group", "select", "from", "where", "table", "user", "limit",
                "by", "desc", "asc", "all", "and", "or", "not", "end", "case", "to", "in"}

# Used to decide if a text value looks like a date at all (has a year-like part
# and a separator), before we spend time trying to parse it.
DATE_HINT = re.compile(
    r"^\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ,]\s*\d{2,4}|[A-Za-z]{3,9} \d{1,2},? \d{4})")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def is_text(series: pd.Series) -> bool:
    """True for text columns (Pandas calls them 'object' or 'str')."""
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


def clean_column_name(name) -> str:
    """Turn any header into a safe snake_case name: 'Unit Price (INR)' -> 'unit_price_inr'."""
    text = str(name).strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)        # camelCase -> camel_Case
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    if not text:
        text = "column"
    if text[0].isdigit():
        text = "col_" + text
    if text in SQL_RESERVED:
        text = text + "_col"
    return text[:60]


def parse_dates(series: pd.Series) -> pd.Series:
    """
    Parse a text column that may contain several date formats.

    First we read the clear international format (2024-03-15). Everything that
    is left is read day-first (15/03/2024, 15-Mar-2024), which is how dates
    are written in India. Values that cannot be read become missing.
    """
    result = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    remaining = result.isna() & series.notna()
    if remaining.any():
        result[remaining] = pd.to_datetime(series[remaining], format="mixed", dayfirst=True,
                                           errors="coerce")
    return result


def to_number(series: pd.Series) -> pd.Series:
    """Read numbers stored as text such as '1,299.50', 'Rs. 500', '12%'."""
    # ₹ is the rupee sign
    stripped = series.astype("string").str.replace(r"(?i)rs\.?|inr|₹|,|%|\s", "", regex=True)
    return pd.to_numeric(stripped, errors="coerce").astype("float64")


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def clean_dataframe(raw: pd.DataFrame):
    """
    Clean a raw table.

    Returns (clean_table, summary). The summary is a dictionary that the
    frontend shows to the user, for example:
        {"rows_before": 10115, "rows_after": 9996,
         "steps": [{"step": "Remove duplicate rows", "detail": "...", "rows_affected": 119}, ...]}
    """
    df = raw.copy()
    steps = []

    def record(step, detail, rows_affected):
        steps.append({"step": step, "detail": detail, "rows_affected": int(rows_affected)})

    rows_before, columns_before = df.shape

    # ---- 1. Clean column names -------------------------------------------
    new_names, used = [], set()
    for original in df.columns:
        name = clean_column_name(original)
        base, counter = name, 2
        while name in used:                     # two headers must not end up the same
            name = f"{base}_{counter}"
            counter += 1
        used.add(name)
        new_names.append(name)
    renamed = {str(old): new for old, new in zip(df.columns, new_names) if str(old) != new}
    df.columns = new_names
    record("Clean column names",
           f"{len(renamed)} column name(s) changed to lower case with underscores."
           if renamed else "All column names were already clean.", 0)

    # ---- 2. Tidy text ----------------------------------------------------
    trimmed_rows = pd.Series(False, index=df.index)
    for column in df.columns:
        if not is_text(df[column]):
            continue
        as_text = df[column].astype("string")
        stripped = as_text.str.strip()
        trimmed_rows |= (as_text != stripped).fillna(False)
        stripped = stripped.mask(stripped.str.lower().isin(MISSING_WORDS))
        df[column] = stripped.astype("object").where(stripped.notna(), None)
    record("Trim extra spaces", "Removed spaces at the start or end of text values.",
           trimmed_rows.sum())

    # ---- 3. Remove fully empty rows and columns --------------------------
    empty_columns = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty_columns)
    empty_rows = int(df.isna().all(axis=1).sum())
    df = df.dropna(how="all")
    record("Remove empty rows and columns",
           f"Removed {empty_rows} empty row(s) and {len(empty_columns)} empty column(s).", empty_rows)

    # Count missing values now, before we fill anything (shown in the overview).
    missing_before = {c: int(df[c].isna().sum()) for c in df.columns}

    # ---- 4. Fix data types -----------------------------------------------
    type_changes, bad_values, dates_reformatted = [], 0, 0
    for column in df.columns:
        if not is_text(df[column]):
            continue
        values = df[column].dropna()
        if values.empty:
            continue

        # 4a. Numbers stored as text. Convert if at least 95% of values are numbers.
        numbers = to_number(df[column])
        if numbers.notna().sum() >= 0.95 * len(values):
            bad_values += len(values) - int(numbers.notna().sum())
            df[column] = numbers
            type_changes.append(f"{column} -> number")
            continue

        # 4b. Dates stored as text. Convert if at least 90% of values are dates.
        sample = values.astype(str).head(200)
        if sample.str.match(DATE_HINT).mean() >= 0.9:
            dates = parse_dates(df[column].astype("string"))
            if dates.notna().sum() >= 0.9 * len(values):
                iso_style = values.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}").sum()
                dates_reformatted += len(values) - int(iso_style)
                bad_values += len(values) - int(dates.notna().sum())
                df[column] = dates
                type_changes.append(f"{column} -> date")
    record("Fix data types",
           ("Converted: " + ", ".join(type_changes) + ".") if type_changes
           else "All columns already had the right type.", bad_values)
    if dates_reformatted:
        record("Standardise date formats",
               "Dates written in different styles (for example 15/03/2024 or 15-Mar-2024) "
               "were converted to one format. Unclear dates are read day first.", dates_reformatted)

    # ---- 5. Fix inconsistent capital letters -----------------------------
    case_rows, case_columns = 0, []
    for column in df.columns:
        if not is_text(df[column]):
            continue
        values = df[column].dropna().astype(str)
        if values.empty:
            continue
        # Count each spelling, then group spellings that differ only by capitals.
        counts = values.value_counts()
        best_spelling = {}
        for spelling, count in counts.items():        # most common spelling comes first
            best_spelling.setdefault(spelling.lower(), spelling)
        mapping = {s: best_spelling[s.lower()] for s in counts.index if best_spelling[s.lower()] != s}
        if mapping:
            affected = int(values.isin(list(mapping)).sum())
            df[column] = df[column].replace(mapping)
            case_rows += affected
            case_columns.append(column)
    record("Fix inconsistent capital letters",
           ("Values like 'north' and 'NORTH' were changed to the most common spelling in: "
            + ", ".join(case_columns) + ".") if case_columns else "No inconsistent spellings found.",
           case_rows)

    # ---- 6. Remove duplicate rows ----------------------------------------
    duplicate_rows = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)
    record("Remove duplicate rows", f"Removed {duplicate_rows} row(s) that were exact copies.",
           duplicate_rows)

    # ---- 7. Fill missing values ------------------------------------------
    filled_rows = pd.Series(False, index=df.index)
    fill_notes = []
    for column in df.columns:
        missing = df[column].isna()
        if not missing.any():
            continue
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            fill_notes.append(f"{column}: {int(missing.sum())} left empty (a date cannot be guessed)")
            continue
        if pd.api.types.is_bool_dtype(df[column]):
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            median = df[column].median()
            if pd.api.types.is_integer_dtype(df[column]):
                median = int(round(median))
            df[column] = df[column].fillna(median)
            fill_notes.append(f"{column}: {int(missing.sum())} filled with the median ({median:g})")
        else:
            df[column] = df[column].fillna("Unknown")
            fill_notes.append(f"{column}: {int(missing.sum())} filled with 'Unknown'")
        filled_rows |= missing
    record("Fill missing values",
           "; ".join(fill_notes) + "." if fill_notes else "No missing values found.",
           filled_rows.sum())

    # Whole numbers that Pandas read as decimals (for example 3.0) become integers again.
    for column in df.columns:
        if pd.api.types.is_float_dtype(df[column]) and df[column].notna().all():
            if (df[column] % 1 == 0).all() and df[column].abs().max() < 2**53:
                df[column] = df[column].astype("int64")

    summary = {
        "rows_before": int(rows_before),
        "rows_after": int(len(df)),
        "columns_before": int(columns_before),
        "columns_after": int(df.shape[1]),
        "renamed_columns": renamed,
        "missing_before": missing_before,
        "steps": steps,
    }
    return df, summary


def read_uploaded_file(file_path: str, original_name: str) -> pd.DataFrame:
    """Read a CSV or Excel file into a table. Everything is read as text first,
    so the cleaning step decides the types itself."""
    lower_name = original_name.lower()
    if lower_name.endswith(".csv"):
        try:
            return pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding="latin-1")
    if lower_name.endswith(".xlsx"):
        return pd.read_excel(file_path, dtype=str, keep_default_na=False)
    raise ValueError("Only CSV (.csv) and Excel (.xlsx) files are supported.")
