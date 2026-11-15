"""
llm_client.py
-------------
Talks to the LLM through OpenRouter (an OpenAI-compatible API).

It is built around the real limits of the free tier:

  - Rate limits. The app counts its own requests (per minute and per day) and
    stops politely BEFORE OpenRouter blocks us. The daily count is kept in a
    small file, so it survives a restart.
  - The free endpoint is sometimes down. Each call is retried with a growing
    wait (backoff). If the main model still fails, LLM_FALLBACK_MODEL is tried.
  - The model cannot be forced to answer in JSON (no response_format). So we
    ask for JSON in the prompt and extract_json() digs it out of the reply.

Nothing in this file knows about SQL or datasets. It only sends messages and
returns text. Reading JSON out of a reply is done in json_parsing.py.
"""

import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone

import httpx

from app.config import STORAGE_DIR, get_settings

settings = get_settings()
logger = logging.getLogger("bi_agent.llm")

ATTEMPTS_PER_MODEL = 2            # first try + one retry
BACKOFF_SECONDS = [2, 5]          # wait before retry 1, retry 2
REQUEST_TIMEOUT_SECONDS = 60
USAGE_FILE = STORAGE_DIR / "llm_usage.json"


class LLMError(Exception):
    """Any LLM problem. user_message is safe and friendly enough to show on screen."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class LLMRateLimitError(LLMError):
    """We have used up the free requests for this minute or this day."""


class LLMUnavailableError(LLMError):
    """The model did not answer even after retries and the fallback model."""


# ---------------------------------------------------------------------------
# Counting our own requests
# ---------------------------------------------------------------------------

_recent_calls = deque()            # times of the calls made in the last minute


def _today() -> str:
    # OpenRouter resets its daily limit at midnight UTC, so we count in UTC too.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_daily_count() -> int:
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        return int(data["count"]) if data.get("date") == _today() else 0
    except (OSError, ValueError, KeyError):
        return 0


def _record_call() -> None:
    _recent_calls.append(time.monotonic())
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps({"date": _today(), "count": _read_daily_count() + 1}),
                          encoding="utf-8")


def usage_status() -> dict:
    """How much of the free quota is used. Shown in the app's top bar."""
    now = time.monotonic()
    while _recent_calls and now - _recent_calls[0] > 60:
        _recent_calls.popleft()
    return {
        "mode": "mock" if settings.is_mock else "live",
        "model": None if settings.is_mock else settings.llm_model,
        "calls_today": _read_daily_count(),
        "daily_limit": settings.llm_max_calls_per_day,
        "calls_last_minute": len(_recent_calls),
        "minute_limit": settings.llm_max_calls_per_minute,
    }


def _check_budget() -> None:
    """Stop before sending if we are at the free tier limit."""
    status = usage_status()
    if status["calls_today"] >= status["daily_limit"]:
        raise LLMRateLimitError(
            f"Today's free AI limit ({status['daily_limit']} requests) has been used up. "
            "It resets at midnight UTC (5:30 am IST). Questions you asked before still work "
            "from saved answers, and you can switch to mock mode for a demo.")
    if status["calls_last_minute"] >= status["minute_limit"]:
        raise LLMRateLimitError(
            "Too many AI requests in the last minute. Please wait about a minute and try again.")


# ---------------------------------------------------------------------------
# Sending one chat request
# ---------------------------------------------------------------------------

def chat(messages: list[dict], max_tokens: int = 1200) -> tuple[str, str]:
    """
    Send a conversation to the LLM and return (reply_text, model_that_answered).

    Tries the main model, then the fallback model (if one is set). Each model
    gets ATTEMPTS_PER_MODEL tries with a wait in between.
    Raises LLMRateLimitError, LLMUnavailableError or LLMError.
    """
    if not settings.openrouter_api_key:
        raise LLMError("No OpenRouter API key is set. Add OPENROUTER_API_KEY to the .env file, "
                       "or set LLM_MODE=mock.")

    models = [m for m in (settings.llm_model, settings.llm_fallback_model) if m]
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}",
               "Content-Type": "application/json"}
    last_problem = "no model is configured (set LLM_MODEL in .env)"

    for model in models:
        for attempt in range(ATTEMPTS_PER_MODEL):
            _check_budget()
            _record_call()
            body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
            try:
                response = httpx.post(f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                                      headers=headers, json=body, timeout=REQUEST_TIMEOUT_SECONDS)
            except httpx.HTTPError as error:               # no internet, timeout, DNS ...
                last_problem = f"network problem ({type(error).__name__})"
                logger.warning("LLM call failed: %s", last_problem)
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue

            if response.status_code == 200:
                text = _reply_text(response)
                if text:
                    return text, model
                last_problem = "the model returned an empty reply"
            elif response.status_code in (401, 403):
                raise LLMError("OpenRouter rejected the API key. Check OPENROUTER_API_KEY in the .env file.")
            elif response.status_code == 402:
                raise LLMError("OpenRouter says this account has no credit for the chosen model. "
                               "Use a model whose name ends with ':free'.")
            elif response.status_code == 429:
                detail = _error_text(response)
                if "per-day" in detail or "per day" in detail or "daily" in detail:
                    raise LLMRateLimitError(
                        "OpenRouter's free daily limit has been reached. It resets at midnight UTC "
                        "(5:30 am IST). Saved answers still work, and mock mode is available for a demo.")
                last_problem = "the model is busy (rate limited)"
            elif response.status_code in (400, 404):
                last_problem = f"model '{model}' was not accepted: {_error_text(response)[:150]}"
                logger.warning("LLM call failed: %s", last_problem)
                break                                       # retrying the same model will not help
            else:
                last_problem = f"OpenRouter returned error {response.status_code}"

            logger.warning("LLM call failed (%s, attempt %d): %s", model, attempt + 1, last_problem)
            if attempt < ATTEMPTS_PER_MODEL - 1:
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])

    raise LLMUnavailableError(
        "The AI model is not available right now (" + last_problem + "). "
        "Free models are sometimes busy. Please try again in a minute.")


def _reply_text(response: httpx.Response) -> str:
    """Pull the assistant's text out of an OpenAI-style response."""
    try:
        content = response.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError):
        return ""
    # Some models print their thinking inside <think> tags. Remove it.
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def _error_text(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json().get("error", "")).lower()
    except ValueError:
        return response.text[:300].lower()
