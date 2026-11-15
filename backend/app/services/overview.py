"""
overview.py
-----------
Automatic overview (exploratory data analysis) of a clean dataset.

It is computed once, right after upload, and saved with the dataset. It gives:
  - KPI cards
  - summary statistics for every number column
  - missing value counts (as they were before cleaning)
  - distributions (histograms for numbers, top values for categories)
  - correlations between number columns
  - 4 to 6 charts chosen automatically

Everything here is plain Pandas. No LLM is used for the overview.

Chart format (the same format is used for answers on the Ask page):
    {"type": "bar" | "line" | "pie" | "histogram" | "heatmap" | "kpi" | "scatter" | "table",
     "title": "...", "x_label": "...", "y_label": "...",
     "x": [...], "series": [{"name": "...", "values": [...]}]}
"""

import numpy as np
import pandas as pd

from app.services.profiling import column_roles, pick_main_metric, to_plain


def nice(name: str) -> str:
    """'product_category' -> 'Product Category' (for titles and labels)."""
    return name.replace("_", " ").title()


def _histogram(series: pd.Series, bins: int = 20) -> dict:
    """Bucket a number column. The top 1% of values are grouped into the last bar
    so that a few very large values do not flatten the whole chart."""
    values = series.dropna().astype(float)
    cap = values.quantile(0.99)
    counts, edges = np.histogram(values.clip(upper=cap), bins=bins)
    return {"x": [round(float(e), 2) for e in edges[:-1]], "counts": [int(c) for c in counts]}


def build_overview(df: pd.DataFrame, cleaning_summary: dict) -> dict:
    roles = column_roles(df)
    measures, categories, dates = roles["measures"], roles["categories"], roles["dates"]
    metric = pick_main_metric(measures)
    date_column = dates[0] if dates else None
    # Categories with fewer different values come first (they make cleaner charts).
    categories = sorted([c for c in categories if df[c].nunique() >= 2], key=lambda c: df[c].nunique())

    # ---------------- KPI cards ----------------
    kpis = [{"label": "Rows", "value": int(len(df)), "kind": "number"},
            {"label": "Columns", "value": int(df.shape[1]), "kind": "number"}]
    if metric:
        kpis.append({"label": f"Total {nice(metric)}", "value": to_plain(df[metric].sum()), "kind": "number"})
        kpis.append({"label": f"Average {nice(metric)}", "value": to_plain(df[metric].mean()), "kind": "number"})
        others = [m for m in measures if m != metric]
        second = pick_main_metric([m for m in others if "profit" in m.lower()] or others)
        if second:
            kpis.append({"label": f"Total {nice(second)}", "value": to_plain(df[second].sum()), "kind": "number"})
    if date_column and df[date_column].notna().any():
        kpis.append({"label": "Date Range", "kind": "text",
                     "value": f"{df[date_column].min():%d %b %Y} to {df[date_column].max():%d %b %Y}"})

    # ---------------- Summary statistics ----------------
    summary_stats = []
    for column in measures:
        s = df[column]
        summary_stats.append({
            "column": column, "count": int(s.count()), "mean": to_plain(s.mean()),
            "median": to_plain(s.median()), "std": to_plain(s.std()),
            "min": to_plain(s.min()), "max": to_plain(s.max()),
        })

    # ---------------- Missing values (before cleaning) ----------------
    rows_before = max(cleaning_summary.get("rows_before", len(df)), 1)
    missing = [{"column": column, "missing": count, "percent": round(100 * count / rows_before, 2)}
               for column, count in cleaning_summary.get("missing_before", {}).items()]

    # ---------------- Distributions ----------------
    distributions = []
    for column in measures[:6]:
        h = _histogram(df[column])
        distributions.append({"type": "histogram", "title": nice(column), "x_label": nice(column),
                              "y_label": "Rows", "x": h["x"],
                              "series": [{"name": "Rows", "values": h["counts"]}]})
    for column in categories[:6]:
        counts = df[column].value_counts().head(8)
        distributions.append({"type": "bar", "title": nice(column), "x_label": nice(column),
                              "y_label": "Rows", "x": [str(v) for v in counts.index],
                              "series": [{"name": "Rows", "values": [int(v) for v in counts.values]}]})

    # ---------------- Correlations ----------------
    correlations = None
    if len(measures) >= 2:
        matrix = df[measures].corr().round(2).fillna(0)
        correlations = {"columns": measures, "matrix": matrix.values.tolist()}

    # ---------------- Auto-selected charts (up to 6) ----------------
    charts = []

    def total_by(category, top=None):
        """Sum of the main metric per category (or row count if there is no metric)."""
        grouped = df.groupby(category)[metric].sum() if metric else df[category].value_counts()
        grouped = grouped.sort_values(ascending=False)
        return grouped.head(top) if top else grouped

    value_name = nice(metric) if metric else "Rows"

    # 1. Trend over time
    if date_column and metric:
        monthly = df.set_index(date_column)[metric].resample("MS").sum()
        charts.append({"type": "line", "title": f"Monthly {value_name}",
                       "x_label": "Month", "y_label": value_name,
                       "x": [d.strftime("%Y-%m-%d") for d in monthly.index],
                       "series": [{"name": value_name, "values": [to_plain(v) for v in monthly.values]}]})

    # 2 and 3. Bar charts for up to two categories, 4. a pie chart for a small category
    bar_candidates = [c for c in categories if df[c].nunique() <= 12]
    pie_column = None
    if len(bar_candidates) >= 3:
        pie_column = bar_candidates[1] if df[bar_candidates[1]].nunique() <= 6 else None
    for column in [c for c in bar_candidates if c != pie_column][:2]:
        grouped = total_by(column)
        charts.append({"type": "bar", "title": f"{value_name} by {nice(column)}",
                       "x_label": nice(column), "y_label": value_name,
                       "x": [str(v) for v in grouped.index],
                       "series": [{"name": value_name, "values": [to_plain(v) for v in grouped.values]}]})
    if pie_column:
        grouped = total_by(pie_column)
        charts.append({"type": "pie", "title": f"Share of {value_name} by {nice(pie_column)}",
                       "x": [str(v) for v in grouped.index],
                       "series": [{"name": value_name, "values": [to_plain(v) for v in grouped.values]}]})

    # 5. Top 10 of a larger category (for example city or state)
    large = [c for c in categories if df[c].nunique() > 12]
    if large and len(charts) < 5:
        grouped = total_by(large[0], top=10)
        charts.append({"type": "bar", "orientation": "h",
                       "title": f"Top 10 {nice(large[0])} by {value_name}",
                       "x_label": nice(large[0]), "y_label": value_name,
                       "x": [str(v) for v in grouped.index],
                       "series": [{"name": value_name, "values": [to_plain(v) for v in grouped.values]}]})

    # 6. Correlation heatmap
    if correlations and len(measures) >= 3 and len(charts) < 6:
        charts.append({"type": "heatmap", "title": "Correlation between number columns",
                       "x": [nice(m) for m in measures], "y": [nice(m) for m in measures],
                       "z": correlations["matrix"]})

    # If the dataset had almost nothing to chart, at least show one distribution.
    if len(charts) < 4:
        charts.extend(distributions[: 4 - len(charts)])

    return {
        "kpis": kpis,
        "summary_stats": summary_stats,
        "missing": missing,
        "distributions": distributions,
        "correlations": correlations,
        "charts": charts[:6],
        "roles": roles,
        "main_metric": metric,
    }
