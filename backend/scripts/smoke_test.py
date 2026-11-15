"""
smoke_test.py
-------------
A quick end-to-end check of the whole backend, from upload to PDF export.
Run it after setup to confirm that everything works on your laptop.

Before running it:
  1. PostgreSQL is running and setup_database.py has been run.
  2. The backend is running in another terminal:   uvicorn app.main:app
  3. LLM_MODE=mock in the .env file (the test uses the fixed demo questions).

How to run (from the backend folder, with the virtual environment active):
    python scripts/smoke_test.py

It logs in as the demo user, uploads the sample CSV, and checks every feature.
At the end it deletes the dataset it uploaded, so it leaves nothing behind.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import PROJECT_ROOT, get_settings  # noqa: E402

BASE_URL = "http://localhost:8000"
SAMPLE_CSV = PROJECT_ROOT / "data" / "indian_retail_sales.csv"
OUTPUT_PDF = PROJECT_ROOT / "backend" / "storage" / "smoke_test_report.pdf"

passed = 0


def check(name: str, condition: bool, detail: str = ""):
    """Print PASS or stop at the first FAIL."""
    global passed
    if not condition:
        print(f"  FAIL  {name}  {detail}")
        sys.exit(1)
    passed += 1
    print(f"  PASS  {name}  {detail}")


def main():
    settings = get_settings()
    client = httpx.Client(base_url=BASE_URL, timeout=120)

    print("1. Server")
    try:
        health = client.get("/api/health").json()
    except httpx.HTTPError:
        sys.exit(f"Cannot reach the backend at {BASE_URL}. Start it first: uvicorn app.main:app")
    check("backend is running", health["status"] == "ok", f"(LLM mode: {health['llm_mode']})")
    if health["llm_mode"] != "mock":
        sys.exit("This test needs LLM_MODE=mock in the .env file. Change it and restart the backend.")
    check("API docs page opens", client.get("/docs").status_code == 200)

    print("2. Login")
    response = client.post("/api/auth/login", data={"username": "nobody@example.com", "password": "wrong-password"})
    check("wrong login is rejected", response.status_code == 401)
    check("request without a token is rejected", client.get("/api/datasets").status_code == 401)
    response = client.post("/api/auth/login", data={"username": settings.demo_user_email,
                                                    "password": settings.demo_user_password})
    check("demo user can log in", response.status_code == 200)
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    check("demo user is not an admin", client.get("/api/admin/users").status_code == 403)

    print("3. Upload and cleaning")
    with SAMPLE_CSV.open("rb") as file:
        response = client.post("/api/datasets", data={"name": "Smoke Test Sales"},
                               files={"file": (SAMPLE_CSV.name, file, "text/csv")})
    check("sample CSV uploads", response.status_code == 200, response.text[:200] if response.status_code != 200 else "")
    dataset = response.json()
    dataset_id = dataset["dataset_id"]
    summary = dataset["cleaning_summary"]
    check("duplicate rows were removed", summary["rows_after"] < summary["rows_before"],
          f"({summary['rows_before']} -> {summary['rows_after']} rows)")
    check("cleaning summary lists its steps", len(summary["steps"]) >= 6)
    types = {c["name"]: c["type"] for c in dataset["schema_info"]["columns"]}
    check("order_date became a date and revenue a number",
          types["order_date"] == "date" and types["revenue"] == "decimal")

    try:
        print("4. Overview")
        overview = client.get(f"/api/datasets/{dataset_id}/overview").json()["overview"]
        check("overview has 4 to 6 charts", 4 <= len(overview["charts"]) <= 6, f"({len(overview['charts'])} charts)")
        check("overview has KPI cards and statistics", overview["kpis"] and overview["summary_stats"])
        check("preview returns rows", len(client.get(f"/api/datasets/{dataset_id}/preview").json()["rows"]) > 0)

        print("5. Ask")

        def ask(question):
            return client.post("/api/ask", json={"dataset_id": dataset_id, "question": question}).json()

        answer = ask("Which region had the highest revenue last quarter?")
        check("question is answered", answer["status"] == "success", f"({answer['result']['rows'][0][0]} is first)")
        check("answer has SQL, chart and insight",
              answer["sql"].upper().startswith("SELECT") and answer["chart"]["type"] == "bar" and answer["insight"])
        check("row limit was added to the SQL", "LIMIT" in answer["sql"].upper())
        again = ask("Which region had the highest revenue last quarter?")
        check("same question comes from the cache", again["cached"] is True)
        check("single value gives a KPI card", ask("What is the total revenue?")["chart"]["type"] == "kpi")
        check("time series gives a line chart", ask("Show the monthly revenue trend")["chart"]["type"] == "line")
        check("unclear question gets a clarifying question", ask("Show me the best one")["status"] == "clarification")
        blocked = ask("Delete all orders from the East region")
        check("harmful query is blocked", blocked["status"] == "blocked")
        check("data is untouched after the blocked query",
              client.get(f"/api/datasets/{dataset_id}").json()["row_count"] == summary["rows_after"]
              and ask("How many orders are there?")["result"]["rows"][0][0] == summary["rows_after"])

        print("6. History")
        history = client.get("/api/history", params={"dataset_id": dataset_id}).json()
        check("history has the questions", len(history) >= 5, f"({len(history)} items)")

        print("7. Forecast")
        response = client.post("/api/forecast", json={"dataset_id": dataset_id})
        check("forecast runs", response.status_code == 200, response.text[:200] if response.status_code != 200 else "")
        forecast = response.json()
        scores = forecast["evaluation"]["scores"]
        check("at least two models were compared with MAE and RMSE",
              len(scores) >= 2 and all("mae" in s and "rmse" in s for s in scores))
        check("the model with the lowest RMSE was chosen",
              forecast["model_name"] == min(scores, key=lambda s: s["rmse"])["model"], f"({forecast['model_name']})")
        check("forecast covers 3 months", len(forecast["output"]["forecast"]) == 3)

        print("8. PDF report")
        report = client.post(f"/api/reports/{answer['analysis_id']}").json()
        pdf = client.get(f"/api/reports/{report['report_id']}/download")
        check("report downloads as a PDF", pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
              f"({len(pdf.content) // 1024} KB)")
        OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PDF.write_bytes(pdf.content)
        forecast_report = client.post(f"/api/reports/{forecast['analysis']['analysis_id']}")
        check("forecast can be exported too", forecast_report.status_code == 200)
        check("reports are listed", len(client.get("/api/reports").json()) >= 2)

        print("9. Admin")
        admin = httpx.Client(base_url=BASE_URL, timeout=60)
        token = admin.post("/api/auth/login", data={"username": settings.admin_email,
                                                    "password": settings.admin_password}).json()["access_token"]
        admin.headers["Authorization"] = "Bearer " + token
        check("admin sees all users", len(admin.get("/api/admin/users").json()) >= 2)
        check("admin sees the demo user's dataset",
              any(d["dataset_id"] == dataset_id for d in admin.get("/api/admin/datasets").json()))
    finally:
        # Clean up, even if a check failed.
        client.delete(f"/api/datasets/{dataset_id}")

    print(f"\nAll {passed} checks passed. A sample report was saved to:\n  {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
