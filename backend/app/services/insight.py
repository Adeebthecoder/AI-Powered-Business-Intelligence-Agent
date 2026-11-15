"""
insight.py
----------
Two jobs:

1. numbers_are_grounded()
   After the LLM writes its 2 to 3 line explanation, we pull every number out
   of that text and check that each one really appears in the query result.
   If even one number cannot be found, the explanation is thrown away.
   This is how we enforce "the AI must not invent values".

2. template_insight()
   A plain, rule-based explanation built directly from the result. It is used
   in mock mode, and as the safe fallback when the LLM's text fails the check
   or the LLM is not available.

No database and no LLM code in this file, so it is easy to test.
"""

import re

from app.services.chart_selector import column_types

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# A number in text: 1,23,456.78 or 42 or 0.35. It must not be glued to a
# letter, so "5G", "Q4" and "128GB" are NOT read as numbers.
NUMBER_IN_TEXT = re.compile(r"(?<![\w])(?<!\d\.)\d[\d,]*(?:\.\d+)?(?![\w])")

# Words after a number that scale it: "7.56 crore" means 75,600,000.
UNIT_WORDS = {
    "thousand": 1e3, "k": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "million": 1e6, "mn": 1e6, "crore": 1e7, "crores": 1e7, "cr": 1e7, "billion": 1e9, "bn": 1e9,
}
UNIT_AFTER = re.compile(r"^\s*(" + "|".join(UNIT_WORDS) + r")\b", re.IGNORECASE)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def extract_numbers(text: str) -> list[dict]:
    """
    Find the numbers in a sentence.
    Returns a list like [{"value": 7.56, "decimals": 2, "scale": 1e7, "percent": False, "raw": "7.56"}].
    """
    found = []
    for match in NUMBER_IN_TEXT.finditer(text):
        raw = match.group().rstrip(",")
        digits = raw.replace(",", "")
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        after = text[match.end():]
        unit = UNIT_AFTER.match(after)
        found.append({
            "value": float(digits),
            "decimals": decimals,
            "scale": UNIT_WORDS[unit.group(1).lower()] if unit else 1.0,
            "percent": after.lstrip().startswith("%") or after.lstrip().lower().startswith("percent"),
            "raw": raw,
        })
    return found


def _allowed_values(rows: list, question: str) -> tuple[list[float], set[float]]:
    """
    Collect what the insight is allowed to mention:
      result_values  every number cell in the result (rounding is tolerated)
      exact_values   numbers that appear inside text cells (for example the
                     2025 in '2025-10-01') or in the user's own question
    """
    result_values, exact_values = [], set()
    for row in rows:
        for cell in row:
            if _is_number(cell):
                result_values.append(abs(float(cell)))
            elif isinstance(cell, str):
                # split dates like 2025-10-01 into 2025, 10 and 1
                for part in re.findall(r"\d+(?:\.\d+)?", cell):
                    exact_values.add(float(part))
    for item in extract_numbers(question):
        exact_values.add(item["value"])
    return result_values, exact_values


def numbers_are_grounded(insight: str, rows: list, question: str = "") -> tuple[bool, list[str]]:
    """
    Check every number in the insight against the result.

    Returns (True, []) if all numbers are supported, otherwise
    (False, [list of numbers that were not found]).

    A number is accepted when it is:
      - a result value, possibly rounded        (75567862.25 -> "75,567,862")
      - a result value in lakh / crore / million ("7.56 crore")
      - a fraction shown as a percentage         (0.34 -> "34%")
      - a number from the question or from a text cell ("top 5", "2025")
      - a small count of rows                    ("the 3 regions")
    """
    result_values, exact_values = _allowed_values(rows, question)
    unsupported = []
    for item in extract_numbers(insight):
        value, scale = item["value"], item["scale"]
        # How far off may the number be? Half of its last written digit.
        # Example: "7.56" may stand for anything from 7.555 to 7.565.
        tolerance = 0.5 * (10 ** -item["decimals"]) * 1.0001

        ok = value in exact_values
        if not ok:
            for real in result_values:
                if abs(value * scale - real) <= tolerance * scale:
                    ok = True                      # same number, maybe rounded or in lakh/crore
                elif item["percent"] and abs(value - real * 100) <= tolerance:
                    ok = True                      # 0.34 written as 34%
                if ok:
                    break
        if not ok and item["decimals"] == 0 and scale == 1.0 and value <= min(len(rows), 10):
            ok = True                              # "the top 3", "all 4 regions"
        if not ok:
            unsupported.append(item["raw"])
    return (len(unsupported) == 0), unsupported


# ---------------------------------------------------------------------------
# Rule-based insight
# ---------------------------------------------------------------------------

def nice(name: str) -> str:
    return str(name).replace("_", " ")


def format_number(value) -> str:
    """Write a number with Indian digit grouping: 1234567.5 -> 12,34,567.5"""
    if not _is_number(value):
        return str(value)
    negative = value < 0
    if isinstance(value, float):
        # small values such as a 0.0668 discount keep 4 decimals, money keeps 2
        places = 4 if abs(value) < 1 else 2
        text = f"{abs(value):.{places}f}".rstrip("0").rstrip(".")
    else:
        text = str(abs(value))
    whole, _, fraction = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if negative else "") + whole + ("." + fraction if fraction else "")


def _label_text(column_name: str, value) -> str:
    """Show a month start such as 2025-10-01 as 'Oct 2025' when the column is a month."""
    text = str(value)
    if "month" in column_name.lower() and re.fullmatch(r"\d{4}-\d{2}-01", text):
        return f"{MONTH_NAMES[int(text[5:7]) - 1]} {text[:4]}"
    return text


def template_insight(columns: list, rows: list, chart: dict) -> str:
    """Write a short explanation straight from the result, with no LLM."""
    if not rows:
        return "The query ran correctly but returned no rows. Try a wider time period or a different filter."

    first = rows[0]
    # One row: read it out.
    if len(rows) == 1:
        parts = [f"{nice(columns[i])} is {format_number(first[i]) if columns[i].lower() != 'year' else first[i]}"
                 for i in range(len(columns))]
        return "The result shows that " + ", and ".join(parts) + "."

    # Which columns are measures (numbers to compare) and which are labels?
    types = column_types(columns, rows)
    number_indexes = [i for i, c in enumerate(columns) if types[c] == "number"]
    label_indexes = [i for i, c in enumerate(columns) if types[c] != "number"]
    if not number_indexes or not label_indexes:
        return f"The query returned {len(rows)} rows. See the table for the details."

    n = number_indexes[0]
    metric = nice(columns[n])

    def label(row):
        return " / ".join(_label_text(columns[i], row[i]) for i in label_indexes)

    valid = [row for row in rows if row[n] is not None]
    if not valid:
        return f"The query returned {len(rows)} rows, but the {metric} values are empty."
    ranked = sorted(valid, key=lambda row: row[n], reverse=True)

    # A single line over time: start, end, peak and low point.
    if chart.get("type") == "line" and len(chart.get("series", [])) == 1 and len(label_indexes) == 1:
        return (f"{metric.capitalize()} was {format_number(valid[0][n])} in {label(valid[0])} and "
                f"{format_number(valid[-1][n])} in {label(valid[-1])}. "
                f"The highest value was {format_number(ranked[0][n])} in {label(ranked[0])} and the "
                f"lowest was {format_number(ranked[-1][n])} in {label(ranked[-1])}.")

    # Categories with a number: the top two and the bottom one.
    text = f"{label(ranked[0])} has the highest {metric} at {format_number(ranked[0][n])}"
    if len(ranked) > 2:
        text += f", followed by {label(ranked[1])} at {format_number(ranked[1][n])}"
    text += f". The lowest in this result is {label(ranked[-1])} at {format_number(ranked[-1][n])}."
    return text
