"""
chart_selector.py
-----------------
Chooses a chart for a query result using simple rules. No LLM is used here,
so the choice is fast, free and always the same for the same result.

The rules, in order:
  1. One row                         -> KPI cards
  2. A time column + numbers         -> line chart (rows must be in time order;
                                        a ranked list such as "top 5 months" gets bars)
       (with one extra category column -> one line per category)
  3. One category + numbers          -> bar chart
       (a "share / percentage" question with few rows -> pie chart)
  4. Two categories + one number     -> grouped bar chart
  5. Only numbers, many rows         -> scatter chart
  6. Anything else                   -> table only

The output uses the chart format described in overview.py.
"""

import re

DATE_TEXT = re.compile(r"^\d{4}-\d{2}(-\d{2})?")
TIME_WORDS = ("date", "month", "year", "quarter", "week", "day", "period")
SHARE_WORDS = ("share", "percentage", "percent", "proportion", "split", "breakdown", "contribution")
MAX_CHART_POINTS = 30          # more bars than this are unreadable
MAX_SERIES = 8


def nice(name: str) -> str:
    return str(name).replace("_", " ").title()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def column_types(columns, rows) -> dict:
    """Label every result column as 'time', 'number' or 'text'."""
    types = {}
    for index, name in enumerate(columns):
        values = [row[index] for row in rows if row[index] is not None]
        lower = name.lower()
        looks_like_time_name = any(word in lower.split("_") or lower == word for word in TIME_WORDS)
        if values and all(isinstance(v, str) and DATE_TEXT.match(v) for v in values):
            types[name] = "time"
        elif values and all(_is_number(v) for v in values):
            # A number column called "year" or "month" is a time axis, not a measure.
            types[name] = "time" if looks_like_time_name else "number"
        elif looks_like_time_name and values:
            types[name] = "time"                    # for example quarter = "Q1 2025"
        else:
            types[name] = "text"
    return types


def choose_chart(columns: list, rows: list, question: str = "") -> dict:
    """Return a chart description for the result, or {"type": "table"}."""
    title = question.strip().rstrip("?").strip()[:90] or "Result"
    if not rows or not columns:
        return {"type": "table", "title": title}

    types = column_types(columns, rows)
    col = {name: [row[i] for row in rows] for i, name in enumerate(columns)}
    time_cols = [c for c in columns if types[c] == "time"]
    number_cols = [c for c in columns if types[c] == "number"]
    text_cols = [c for c in columns if types[c] == "text"]

    # ---- Rule 1: a single row becomes KPI cards -----------------------------
    if len(rows) == 1 and len(columns) <= 6:
        cards = [{"label": nice(name), "value": col[name][0]} for name in columns]
        return {"type": "kpi", "title": title, "cards": cards}

    # ---- Rule 2: time on the x axis -> line chart ---------------------------
    in_time_order = bool(time_cols) and len(text_cols) <= 1 and (
        len(text_cols) == 1 or [str(v) for v in col[time_cols[0]]] == sorted(str(v) for v in col[time_cols[0]]))
    if time_cols and number_cols and len(rows) >= 2 and in_time_order:
        x_name, y_name = time_cols[0], number_cols[0]
        # 2a. time + one category + number: draw one line per category
        if len(text_cols) == 1 and len(set(col[text_cols[0]])) <= MAX_SERIES:
            x_values = sorted(set(col[x_name]), key=str)
            series = []
            for group in sorted(set(col[text_cols[0]]), key=str):
                lookup = {x: y for x, g, y in zip(col[x_name], col[text_cols[0]], col[y_name]) if g == group}
                series.append({"name": str(group), "values": [lookup.get(x) for x in x_values]})
            return {"type": "line", "title": title, "x_label": nice(x_name), "y_label": nice(y_name),
                    "x": [str(x) for x in x_values], "series": series}
        # 2b. time + numbers: one line per number column of a similar size
        if not text_cols:
            first_max = max((abs(v) for v in col[y_name] if v is not None), default=0) or 1
            series = []
            for name in number_cols[:3]:
                biggest = max((abs(v) for v in col[name] if v is not None), default=0)
                # Skip columns on a very different scale (they would look like a flat line).
                if name == y_name or first_max / 20 <= biggest <= first_max * 20:
                    series.append({"name": nice(name), "values": col[name]})
            # Two points do not make a trend, so use bars for very short series.
            chart_type = "line" if len(rows) >= 3 else "bar"
            return {"type": chart_type, "title": title, "x_label": nice(x_name),
                    "y_label": nice(y_name) if len(series) == 1 else "Value",
                    "x": [str(x) for x in col[x_name]], "series": series}

    # ---- Rule 3: one category + numbers -> bar (or pie) ----------------------
    label_cols = text_cols or time_cols
    if len(label_cols) == 1 and number_cols:
        x_name, y_name = label_cols[0], number_cols[0]
        labels = [str(v) for v in col[x_name]][:MAX_CHART_POINTS]
        values = col[y_name][:MAX_CHART_POINTS]
        wants_share = any(word in question.lower() for word in SHARE_WORDS)
        if wants_share and 2 <= len(labels) <= 8 and all(v is not None and v >= 0 for v in values):
            return {"type": "pie", "title": title, "x": labels,
                    "series": [{"name": nice(y_name), "values": values}]}
        first_max = max((abs(v) for v in values if v is not None), default=0) or 1
        series = []
        for name in number_cols[:3]:
            biggest = max((abs(v) for v in col[name] if v is not None), default=0)
            if name == y_name or first_max / 20 <= biggest <= first_max * 20:
                series.append({"name": nice(name), "values": col[name][:MAX_CHART_POINTS]})
        many_or_long = len(labels) > 8 or max(len(label) for label in labels) > 18
        return {"type": "bar", "title": title, "x_label": nice(x_name),
                "y_label": nice(y_name) if len(series) == 1 else "Value",
                "orientation": "h" if many_or_long and len(series) == 1 else "v",
                "x": labels, "series": series}

    # ---- Rule 4: two categories + one number -> grouped bars -----------------
    if len(label_cols) == 2 and number_cols:
        first, second = label_cols
        # Put the category with fewer values in the legend.
        if len(set(col[first])) < len(set(col[second])):
            first, second = second, first
        groups = sorted(set(col[second]), key=str)
        x_values = list(dict.fromkeys(col[first]))          # keep the result order
        if len(groups) <= MAX_SERIES and len(x_values) <= MAX_CHART_POINTS:
            y_name = number_cols[0]
            series = []
            for group in groups:
                lookup = {x: y for x, g, y in zip(col[first], col[second], col[y_name]) if g == group}
                series.append({"name": str(group), "values": [lookup.get(x) for x in x_values]})
            return {"type": "bar", "title": title, "x_label": nice(first), "y_label": nice(y_name),
                    "orientation": "v", "x": [str(x) for x in x_values], "series": series}

    # ---- Rule 5: only numbers -> scatter -------------------------------------
    if not text_cols and not time_cols and len(number_cols) >= 2 and len(rows) >= 5:
        x_name, y_name = number_cols[0], number_cols[1]
        return {"type": "scatter", "title": title, "x_label": nice(x_name), "y_label": nice(y_name),
                "x": col[x_name], "series": [{"name": nice(y_name), "values": col[y_name]}]}

    # ---- Rule 6: nothing fits -> table only ----------------------------------
    return {"type": "table", "title": title}
