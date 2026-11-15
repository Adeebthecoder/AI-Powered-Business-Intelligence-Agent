"""
report_pdf.py
-------------
Builds the PDF report for one analysis.

The report contains: question, insight, chart, result table, the SQL that
was used, dataset name, timestamp and the project credit line.

  - The page layout is done with ReportLab.
  - The chart is drawn again with Matplotlib from the same chart description
    the frontend uses, then placed in the PDF as an image.
"""

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")              # draw to memory, no window needed
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from app.config import APP_NAME, CREDIT_LINE  # noqa: E402
from app.services.insight import format_number  # noqa: E402

ACCENT = "#4338CA"
SERIES_COLOURS = ["#4338CA", "#0EA5A4", "#F59E0B", "#E11D48", "#64748B", "#7C3AED", "#16A34A", "#0284C7"]
MAX_TABLE_ROWS = 25
MAX_TABLE_COLUMNS = 7


def _latin(text) -> str:
    """The built-in PDF fonts cannot draw the rupee sign and similar characters."""
    return str(text).replace("₹", "Rs. ").encode("latin-1", "replace").decode("latin-1")


def _short_number(value, _position=None) -> str:
    """Axis labels: 2500000 -> 25L, 12000000 -> 1.2Cr (Indian units)."""
    magnitude = abs(value)
    if magnitude >= 1e7:
        return f"{value / 1e7:.1f}Cr"
    if magnitude >= 1e5:
        return f"{value / 1e5:.1f}L"
    if magnitude >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:g}"


def render_chart_png(chart: dict) -> bytes | None:
    """Draw the chart with Matplotlib. Returns PNG bytes, or None for chart types
    that have no picture (KPI cards and plain tables)."""
    chart_type = chart.get("type")
    series = chart.get("series") or []
    x = chart.get("x") or []
    if chart_type not in ("bar", "line", "pie", "scatter", "histogram") or not series or not x:
        return None

    figure, axis = plt.subplots(figsize=(7.2, 3.6), dpi=160)
    try:
        if chart_type == "pie":
            axis.pie(series[0]["values"], labels=x, autopct="%1.1f%%", startangle=90,
                     colors=SERIES_COLOURS, wedgeprops={"edgecolor": "white"}, textprops={"fontsize": 8})
        elif chart_type == "line":
            for index, item in enumerate(series):
                values = [float("nan") if v is None else v for v in item["values"]]
                axis.plot(range(len(x)), values, marker="o", markersize=3, linewidth=1.8,
                          linestyle="--" if item.get("dashed") else "-",
                          color=SERIES_COLOURS[index % len(SERIES_COLOURS)], label=item["name"])
            step = max(1, len(x) // 10)
            axis.set_xticks(range(0, len(x), step))
            axis.set_xticklabels([str(v)[:7] for v in x][::step], rotation=45, ha="right", fontsize=7)
        elif chart_type == "scatter":
            axis.scatter(x, series[0]["values"], s=14, color=ACCENT, alpha=0.7)
        else:                                               # bar and histogram
            positions = range(len(x))
            width = 0.8 / len(series)
            horizontal = chart.get("orientation") == "h"
            for index, item in enumerate(series):
                values = [0 if v is None else v for v in item["values"]]
                offsets = [p + index * width - 0.4 + width / 2 for p in positions]
                colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
                if horizontal:
                    axis.barh(offsets, values, height=width, color=colour, label=item["name"])
                else:
                    axis.bar(offsets, values, width=width, color=colour, label=item["name"])
            labels = [str(v)[:22] for v in x]
            if horizontal:
                axis.set_yticks(list(positions))
                axis.set_yticklabels(labels, fontsize=7)
                axis.invert_yaxis()                         # biggest bar on top
            else:
                axis.set_xticks(list(positions))
                axis.set_xticklabels(labels, rotation=30 if len(x) > 4 else 0,
                                     ha="right" if len(x) > 4 else "center", fontsize=7)

        if chart_type != "pie":
            horizontal = chart.get("orientation") == "h" and chart_type == "bar"
            value_axis = axis.xaxis if horizontal else axis.yaxis
            value_axis.set_major_formatter(plt.FuncFormatter(_short_number))
            axis.tick_params(labelsize=7)
            axis.grid(axis="x" if horizontal else "y", color="#E2E8F0", linewidth=0.6)
            axis.set_axisbelow(True)
            for side in ("top", "right"):
                axis.spines[side].set_visible(False)
            if len(series) > 1:
                axis.legend(fontsize=7, frameon=False)
        figure.tight_layout()
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        plt.close(figure)


def build_report_pdf(path: str, *, title: str, question: str, dataset_name: str, insight: str,
                     sql: str | None, result: dict | None, chart: dict | None,
                     analysis_time: datetime, extra_tables: list[dict] | None = None) -> None:
    """Write the PDF to `path`. extra_tables is used by forecasts to add the model scores."""
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], textColor=colors.HexColor(ACCENT),
                             fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14)
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=colors.HexColor("#64748B"))
    code = ParagraphStyle("Code", parent=body, fontName="Courier", fontSize=8, leading=11,
                          backColor=colors.HexColor("#F1F5F9"), borderPadding=6)
    cell = ParagraphStyle("Cell", parent=body, fontSize=8, leading=10)

    def footer(canvas, document):
        """Drawn on every page: the credit line and the page number."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(18 * mm, 10 * mm, _latin(CREDIT_LINE))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    def make_table(columns, rows):
        columns = columns[:MAX_TABLE_COLUMNS]
        data = [[Paragraph(f"<b>{escape(_latin(c))}</b>", cell) for c in columns]]
        for row in rows[:MAX_TABLE_ROWS]:
            cells = []
            for name, value in zip(columns, row):
                # a year such as 2025 must not be printed as 2,025
                text = "" if value is None else (str(value) if str(name).lower() == "year" else format_number(value))
                cells.append(Paragraph(escape(_latin(text)), cell))
            data.append(cells)
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    story = [
        Paragraph(_latin(APP_NAME), small),
        Paragraph(escape(_latin(title)), ParagraphStyle("Title", parent=styles["Title"], fontSize=17,
                                                        alignment=0, spaceAfter=6)),
        Paragraph(f"<b>Dataset:</b> {escape(_latin(dataset_name))} &nbsp;&nbsp; "
                  f"<b>Analysis time:</b> {analysis_time.astimezone(timezone.utc):%d %b %Y, %H:%M} UTC &nbsp;&nbsp; "
                  f"<b>Report created:</b> {datetime.now(timezone.utc):%d %b %Y, %H:%M} UTC", small),
        Paragraph("Question", heading), Paragraph(escape(_latin(question)), body),
        Paragraph("Insight", heading), Paragraph(escape(_latin(insight or "No insight available.")), body),
    ]

    # KPI results have no picture, so their values are listed as text instead.
    if chart and chart.get("type") == "kpi":
        for card in chart.get("cards", []):
            story.append(Paragraph(f"<b>{escape(_latin(card['label']))}:</b> "
                                   f"{escape(_latin(format_number(card['value'])))}", body))
    png = render_chart_png(chart) if chart else None
    if png:
        story += [Paragraph("Chart", heading), Image(io.BytesIO(png), width=164 * mm, height=82 * mm)]

    if result and result.get("rows"):
        story.append(Paragraph("Result table", heading))
        story.append(make_table(result["columns"], result["rows"]))
        hidden_rows = len(result["rows"]) - MAX_TABLE_ROWS
        hidden_columns = len(result["columns"]) - MAX_TABLE_COLUMNS
        if hidden_rows > 0 or hidden_columns > 0:
            story.append(Paragraph(
                f"Showing the first {min(len(result['rows']), MAX_TABLE_ROWS)} of {len(result['rows'])} rows"
                + (f" and the first {MAX_TABLE_COLUMNS} of {len(result['columns'])} columns" if hidden_columns > 0 else "")
                + ".", small))

    for extra in extra_tables or []:
        story.append(Paragraph(escape(_latin(extra["title"])), heading))
        story.append(make_table(extra["columns"], extra["rows"]))
        if extra.get("note"):
            story.append(Paragraph(escape(_latin(extra["note"])), small))

    if sql:
        story += [Paragraph("SQL used", heading), Paragraph(escape(_latin(sql)), code)]

    story += [Spacer(1, 8 * mm),
              Paragraph("The numbers in this report were computed from the dataset by the system. "
                        "The insight text is an interpretation of those numbers, not a guaranteed "
                        "business decision.", small)]

    document = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=18 * mm,
                                 title=_latin(title), author="Bhumika Panwar and Mohd. Adeeb Siddiqui")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
