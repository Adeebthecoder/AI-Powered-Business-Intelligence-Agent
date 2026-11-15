"""
ask_engine.py
-------------
The "agent": it takes one question and runs the whole flow.

    question
       |
       v
    0. cache        same question on the same dataset before? -> reuse it (0 LLM calls)
    1. LLM call 1   question + schema -> SQL  (or a clarifying question)
    2. safety       sql_safety.check_and_fix_sql()  -> blocked queries are logged
    3. run          read-only database user, with a time limit
                    (if step 1, 2 or 3 fails in a fixable way: ONE retry of call 1)
    4. chart        simple rules, no LLM
    5. LLM call 2   question + result -> short insight
    6. verify       numbers in the insight must exist in the result, else use the
                    rule-based insight instead
    7. save         every outcome is stored in Analysis_History

LLM budget per question: 2 calls, plus at most 1 retry of the SQL call.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATASET_SCHEMA, STORAGE_DIR, get_settings
from app.models import AnalysisHistory, Dataset, User
from app.services import llm_client, mock_llm
from app.services.chart_selector import choose_chart
from app.services.insight import numbers_are_grounded, template_insight
from app.services.json_parsing import extract_json
from app.services.llm_client import LLMError
from app.services.prompts import build_insight_messages, build_sql_messages
from app.services.query_runner import QueryFailedError, run_readonly_query
from app.services.sql_safety import UnsafeQueryError, check_and_fix_sql
from app.services.time_reference import build_time_reference

settings = get_settings()
logger = logging.getLogger("bi_agent.ask")

MAX_SQL_ATTEMPTS = 2               # first try + one retry
BLOCKED_LOG = STORAGE_DIR / "logs" / "blocked_queries.log"


def log_blocked_query(user: User, dataset: Dataset, question: str, sql: str, reason: str) -> None:
    """Write every blocked query to a log file, so it can be reviewed later."""
    BLOCKED_LOG.parent.mkdir(parents=True, exist_ok=True)
    one_line_sql = " ".join(str(sql).split())
    with BLOCKED_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now(timezone.utc).isoformat()} | user={user.user_id} | "
                  f"dataset={dataset.dataset_id} | reason={reason} | question={question!r} | "
                  f"sql={one_line_sql}\n")
    logger.warning("Blocked query for user %s: %s", user.user_id, reason)


def find_cached_answer(db: Session, dataset: Dataset, question_key: str) -> AnalysisHistory | None:
    """The newest successful answer to the same question on the same dataset."""
    return db.scalar(
        select(AnalysisHistory)
        .where(AnalysisHistory.dataset_id == dataset.dataset_id,
               AnalysisHistory.question_key == question_key,
               AnalysisHistory.operation == "nl_query",
               AnalysisHistory.status == "success")
        .order_by(AnalysisHistory.timestamp.desc()).limit(1))


def answer_question(db: Session, user: User, dataset: Dataset, question: str,
                    previous_question: str | None = None,
                    skip_cache: bool = False) -> tuple[AnalysisHistory, bool]:
    """
    Answer one question. Returns (history_row, came_from_cache).

    The history row's "status" tells the frontend what happened:
        success        answer, chart and insight are ready
        clarification  the system needs more detail (text is in error_message)
        blocked        the SQL was unsafe and was not run
        error          something failed (friendly text is in error_message)
    """
    question = question.strip()
    full_question = f"{previous_question.strip()} ({question})" if previous_question else question
    question_key = mock_llm.normalise(full_question)[:500]

    # ---- 0. Cache ------------------------------------------------------------
    if not skip_cache:
        cached = find_cached_answer(db, dataset, question_key)
        if cached is not None:
            return cached, True

    record = AnalysisHistory(
        user_id=user.user_id, dataset_id=dataset.dataset_id, question=full_question,
        question_key=question_key, operation="nl_query", status="error", llm_calls=0,
        model_used="mock" if settings.is_mock else settings.llm_model)

    def finish(status: str, message: str | None = None) -> tuple[AnalysisHistory, bool]:
        record.status = status
        record.error_message = message
        db.add(record)
        db.commit()
        return record, False

    columns = [c["name"] for c in dataset.schema_info["columns"]]
    time_reference = build_time_reference(dataset.schema_info)

    # ---- 1 to 3. Get SQL, check it, run it (with one retry) --------------------
    result, feedback = None, None
    for attempt in range(MAX_SQL_ATTEMPTS):
        last_attempt = attempt == MAX_SQL_ATTEMPTS - 1

        # 1. Ask the LLM (or the mock) for SQL
        try:
            if settings.is_mock:
                # the mock matches on the newest message only (the follow-up to a clarification)
                reply = mock_llm.mock_sql_reply(question, dataset.table_name, columns, time_reference)
            else:
                messages = build_sql_messages(question, dataset.table_name, dataset.schema_info,
                                              time_reference, previous_question, feedback)
                reply, record.model_used = llm_client.chat(messages, max_tokens=1200)
                record.llm_calls += 1
        except LLMError as error:
            return finish("error", error.user_message)

        parsed = extract_json(reply)
        if parsed is None or parsed.get("action") not in ("sql", "clarify"):
            feedback = "The reply was not a valid JSON object with an 'action' of 'sql' or 'clarify'."
            if last_attempt:
                return finish("error", "The AI model did not reply in the expected format. "
                                       "Please try again or rephrase the question.")
            continue

        if parsed["action"] == "clarify":
            text = str(parsed.get("clarifying_question") or "Could you give a little more detail?")
            return finish("clarification", text)

        raw_sql = str(parsed.get("sql") or "")
        record.sql_query = raw_sql

        # 2. Safety check
        try:
            safe_sql = check_and_fix_sql(raw_sql, dataset.table_name, columns,
                                         DATASET_SCHEMA, settings.sql_max_rows)
        except UnsafeQueryError as error:
            log_blocked_query(user, dataset, full_question, raw_sql, error.reason)
            if error.retryable and not last_attempt:
                feedback = error.reason
                continue
            return finish("blocked", "This request was blocked by the safety check, so nothing was run. "
                                     f"Reason: {error.reason}")
        record.sql_query = safe_sql

        # 3. Run it as the read-only user
        try:
            result = run_readonly_query(safe_sql)
            break
        except QueryFailedError as error:
            if error.timed_out:
                return finish("error", f"The query took longer than {settings.sql_timeout_seconds} "
                                       "seconds and was stopped. Try a narrower question.")
            if last_attempt:
                return finish("error", "The database could not run the query the AI wrote. "
                                       f"Please rephrase the question. (Details: {error.message})")
            feedback = f"PostgreSQL error: {error.message}"

    # ---- 4. Chart (rules only) ----------------------------------------------
    chart = choose_chart(result["columns"], result["rows"], full_question)
    record.result_data = result
    record.chart_spec = chart

    # ---- 5 and 6. Insight, then verify its numbers -----------------------------
    fallback = template_insight(result["columns"], result["rows"], chart)
    insight, source, note = fallback, "template", None
    if result["rows"] and not settings.is_mock:
        try:
            messages = build_insight_messages(full_question, result["columns"], result["rows"])
            text, _ = llm_client.chat(messages, max_tokens=600)
            record.llm_calls += 1
            text = " ".join(text.split())
            grounded, unsupported = numbers_are_grounded(text, result["rows"], full_question)
            if grounded:
                insight, source = text, "llm"
            else:
                logger.warning("Insight dropped. Numbers not found in the result: %s", unsupported)
                note = ("The AI's explanation mentioned numbers that are not in the result, so it was "
                        "replaced with an automatic summary.")
        except LLMError as error:
            # The data answer is still good. Only the wording falls back.
            note = "The AI explanation was not available, so an automatic summary is shown. " + error.user_message
    record.result_summary = insight
    record.insight_source = source
    return finish("success", note)
