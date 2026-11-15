"""
run_evaluation.py
-----------------
Marks the system against 20 business questions with known correct answers.

For each question:
  1. The correct answer is computed directly in Pandas (evaluation/questions.py).
  2. The question is sent to the running system through the normal /api/ask
     endpoint, so it goes through the LLM (or mock), the SQL safety check and
     the read-only database user, exactly like a real user's question.
  3. The two answers are compared and the question is marked right or wrong.
At the end an accuracy score is printed and saved to evaluation/last_results.json.

Before running it, start the backend in another terminal:  uvicorn app.main:app

How to run (from the backend folder, with the virtual environment active):
    python scripts/run_evaluation.py              all 20 questions
    python scripts/run_evaluation.py --limit 5    only the first 5
    python scripts/run_evaluation.py --fresh      ignore saved answers and ask again

About the two modes:
  - LLM_MODE=mock  The SQL comes from the fixed mock answers, so this checks
                   that the whole pipeline works and gives correct numbers.
                   It does NOT measure how good the AI model is.
  - LLM_MODE=live  This is the real accuracy test of the AI model. It uses up
                   to 2 LLM calls per question (about 40 of the 50 free daily
                   requests), so run it once and with care. Answers are cached,
                   so running it again the same day costs nothing.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import PROJECT_ROOT, get_settings  # noqa: E402
from app.services.cleaning import clean_dataframe, read_uploaded_file  # noqa: E402
from evaluation.questions import QUESTIONS, is_correct  # noqa: E402

BASE_URL = "http://localhost:8000"
SAMPLE_CSV = PROJECT_ROOT / "data" / "indian_retail_sales.csv"
DATASET_NAME = "Evaluation Sales"
RESULTS_FILE = BACKEND_DIR / "evaluation" / "last_results.json"
SECONDS_BETWEEN_LIVE_QUESTIONS = 7        # 2 calls per question -> stays under 20 calls per minute


def main():
    parser = argparse.ArgumentParser(description="Run the 20 question evaluation.")
    parser.add_argument("--limit", type=int, default=len(QUESTIONS), help="only run the first N questions")
    parser.add_argument("--fresh", action="store_true", help="ignore saved answers and ask the LLM again")
    args = parser.parse_args()
    settings = get_settings()

    # ---- The answer key: clean the CSV with our pipeline, then use plain Pandas
    clean, _ = clean_dataframe(read_uploaded_file(str(SAMPLE_CSV), SAMPLE_CSV.name))

    # ---- Connect to the running system as the demo user
    client = httpx.Client(base_url=BASE_URL, timeout=180)
    try:
        health = client.get("/api/health").json()
    except httpx.HTTPError:
        sys.exit(f"Cannot reach the backend at {BASE_URL}. Start it first: uvicorn app.main:app")
    login = client.post("/api/auth/login", data={"username": settings.demo_user_email,
                                                 "password": settings.demo_user_password})
    if login.status_code != 200:
        sys.exit("Could not log in as the demo user. Check DEMO_USER_EMAIL and DEMO_USER_PASSWORD in .env.")
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]

    # ---- Use the evaluation dataset (upload it the first time)
    existing = [d for d in client.get("/api/datasets").json() if d["name"] == DATASET_NAME]
    if existing:
        dataset_id = existing[0]["dataset_id"]
    else:
        with SAMPLE_CSV.open("rb") as file:
            response = client.post("/api/datasets", data={"name": DATASET_NAME},
                                   files={"file": (SAMPLE_CSV.name, file, "text/csv")})
        response.raise_for_status()
        dataset_id = response.json()["dataset_id"]

    mode = health["llm_mode"]
    print(f"Evaluation of {min(args.limit, len(QUESTIONS))} questions   |   LLM mode: {mode}"
          + (f" ({health['llm_model']})" if mode == "live" else ""))
    print("-" * 100)

    results, correct_count, llm_calls = [], 0, 0
    for number, item in enumerate(QUESTIONS[:args.limit], start=1):
        expected = item["expected"](clean)
        answer = client.post("/api/ask", json={"dataset_id": dataset_id, "question": item["question"],
                                               "skip_cache": args.fresh}).json()
        rows = (answer.get("result") or {}).get("rows") or []
        correct = answer.get("status") == "success" and is_correct(item["kind"], expected, rows)
        correct_count += correct
        llm_calls += 0 if answer.get("cached") else answer.get("llm_calls", 0)

        note = "" if correct else f"   <- status: {answer.get('status')}. {(answer.get('message') or '')[:80]}"
        print(f"{number:>2}. {'CORRECT' if correct else 'WRONG  '}  {item['question']}{note}")
        results.append({"question": item["question"], "correct": bool(correct),
                        "status": answer.get("status"), "sql": answer.get("sql"),
                        "expected": expected if isinstance(expected, (list, str)) else float(expected),
                        "system_first_rows": rows[:5], "cached": answer.get("cached")})

        if mode == "live" and not answer.get("cached") and number < args.limit:
            time.sleep(SECONDS_BETWEEN_LIVE_QUESTIONS)

    total = len(results)
    accuracy = 100 * correct_count / total if total else 0
    print("-" * 100)
    print(f"Accuracy: {correct_count} / {total} = {accuracy:.1f}%      (LLM calls used: {llm_calls})")
    if mode == "mock":
        print("Note: in mock mode the SQL is pre-written, so this score checks the pipeline, not the AI model.")

    RESULTS_FILE.write_text(json.dumps({"mode": mode, "model": health.get("llm_model"),
                                        "correct": correct_count, "total": total,
                                        "accuracy_percent": round(accuracy, 1), "results": results},
                                       indent=2, default=str), encoding="utf-8")
    print(f"Details saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
