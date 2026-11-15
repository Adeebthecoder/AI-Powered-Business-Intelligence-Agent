"""
prompts.py
----------
The exact text we send to the LLM. There are only two prompts:

  1. SQL prompt      question + table schema  ->  one SQL query (or a clarifying question)
  2. Insight prompt  question + query result  ->  2 to 3 sentences in simple business language

What the LLM is allowed to see:
  - the table name, column names and types
  - a few example values and three sample rows
  - the rows returned by the query (never more than MAX_RESULT_ROWS_FOR_LLM)
It never receives the full dataset.
"""

import json

MAX_RESULT_ROWS_FOR_LLM = 30


def describe_schema(table_name: str, schema_info: dict) -> str:
    """Turn the saved schema into a short text block for the prompt."""
    lines = [f"Table: {table_name}   ({schema_info.get('row_count', '?')} rows)", "Columns:"]
    for column in schema_info["columns"]:
        line = f"  - {column['name']} ({column['type']})"
        if "values" in column:                               # small category: list every value
            line += " values: " + ", ".join(repr(v) for v in column["values"])
        elif "min" in column:
            line += f" range: {column['min']} to {column['max']}"
        else:
            line += " examples: " + ", ".join(repr(v) for v in column["examples"])
        lines.append(line)
    lines.append("Sample rows (for format only):")
    for row in schema_info.get("sample_rows", []):
        lines.append("  " + json.dumps(row, ensure_ascii=False, default=str))
    return "\n".join(lines)


SQL_SYSTEM_PROMPT = """You are a careful data analyst who writes PostgreSQL queries for business users.

You will get a table description and a question. Reply with ONE JSON object and nothing else.

If the question can be answered from the table, reply:
{{"action": "sql", "sql": "<one PostgreSQL SELECT query>"}}

If the question is unclear (it does not say what to measure, or it could mean very different things), reply:
{{"action": "clarify", "clarifying_question": "<one short question to the user>"}}
Do not guess when the question is unclear. Ask.

Rules for the SQL:
- Exactly one SELECT statement. No semicolon. Never INSERT, UPDATE, DELETE, DROP or any other statement.
- Use only the table {table} and only the columns listed. Do not invent columns.
- Text values must match the listed values exactly (same capital letters).
- Give every calculated column a clear lower_case name with AS, for example total_revenue.
- Round money and averages to 2 decimals: ROUND(SUM(revenue)::numeric, 2).
- For "which is highest / lowest / top N" questions, return the ranked rows (ORDER BY ... LIMIT), with the name column first and the number column second.
- Return at most 50 rows unless the user asks for more.
{time_rules}
{schema}
"""

TIME_RULES = """- Time words are measured from the latest date in the data ({data_end}), NOT from today's date.
  "last quarter" = {last_quarter_start} to {last_quarter_end} ({last_quarter_name})
  "last month"   = {last_month_start} to {last_month_end}
  "this year"    = {this_year}, "last year" = {last_year}
  The date column is {date_column}. For monthly results use date_trunc('month', {date_column})::date AS month.
"""


def build_sql_messages(question: str, table_name: str, schema_info: dict, time_reference: dict | None,
                       previous_question: str | None = None, feedback: str | None = None) -> list[dict]:
    """Messages for call 1: write the SQL."""
    time_rules = TIME_RULES.format(**time_reference) if time_reference else ""
    system = SQL_SYSTEM_PROMPT.format(table=table_name, time_rules=time_rules,
                                      schema=describe_schema(table_name, schema_info))
    user = f"Question: {question}"
    if previous_question:
        # The user is answering a clarifying question we asked earlier.
        user = (f"Earlier question: {previous_question}\n"
                f"The user then added this to make it clear: {question}\n"
                "Answer the earlier question using this extra detail.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if feedback:
        # Second try: tell the model what was wrong with its first answer.
        messages.append({"role": "user", "content":
                         f"Your previous reply could not be used. Problem: {feedback}\n"
                         "Reply again with one corrected JSON object only."})
    return messages


INSIGHT_SYSTEM_PROMPT = """You explain query results to a business manager.

Write 2 or 3 short sentences in simple business English. Plain text only: no bullet points, no markdown, no headings.

Strict rules about numbers:
- Use ONLY numbers that appear in the result below. Copy them as they are (you may round to a whole number).
- Do NOT calculate anything new: no differences, no sums, no percentages, no averages, no "twice as much".
- Do NOT mention any year, date or quantity that is not in the result or in the question.
- If the result is empty, say that no matching data was found.
Say what stands out (highest, lowest, trend) and why it matters for the business."""


def result_as_text(columns: list, rows: list) -> str:
    """The query result as a small text table (at most MAX_RESULT_ROWS_FOR_LLM rows)."""
    lines = [" | ".join(str(c) for c in columns)]
    for row in rows[:MAX_RESULT_ROWS_FOR_LLM]:
        lines.append(" | ".join("" if v is None else str(v) for v in row))
    if len(rows) > MAX_RESULT_ROWS_FOR_LLM:
        lines.append(f"... ({len(rows) - MAX_RESULT_ROWS_FOR_LLM} more rows not shown)")
    return "\n".join(lines)


def build_insight_messages(question: str, columns: list, rows: list) -> list[dict]:
    """Messages for call 2: explain the result. Note: no schema and no SQL here,
    only the question and the rows that came back."""
    user = (f"Question: {question}\n\nResult ({len(rows)} rows):\n{result_as_text(columns, rows)}")
    return [{"role": "system", "content": INSIGHT_SYSTEM_PROMPT}, {"role": "user", "content": user}]
