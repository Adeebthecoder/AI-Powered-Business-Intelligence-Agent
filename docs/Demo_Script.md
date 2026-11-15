# Demo Script: 5 Minutes

AI-Powered Business Intelligence Agent

Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project

This script works in **mock mode** and in **live mode**. Every question below is in the
mock list, so the demo cannot fail because of the internet.

---

## Before the demo (do this 15 minutes early)

1. Start PostgreSQL (or `docker compose up -d`).
2. Start the backend: `uvicorn app.main:app --reload` and wait for "Application startup complete".
3. Start the frontend: `npm run dev`, then open http://localhost:5173.
4. Run `python scripts/smoke_test.py` once. It must say "All 32 checks passed".
5. Decide the mode:
   - **Safest:** `LLM_MODE=mock` in `.env`.
   - **Live:** `LLM_MODE=live`. The day before, ask every question in this script once, so the answers are saved and cost zero requests on demo day.
6. Log in as the demo user and **delete any old "Retail Sales" dataset**, so the upload step is fresh. (If you run live and already asked the questions, keep the dataset and skip the upload. Saved answers belong to the dataset.)
7. Set the browser zoom to 110% or 125% so the projector is readable. Close other tabs.
8. Keep these open in other tabs: http://localhost:8000/docs and the file `backend/app/services/sql_safety.py` in VS Code.

**If something goes wrong during a live demo:** set `LLM_MODE=mock` in `.env`, restart the backend (Ctrl + C, then the uvicorn command), refresh the browser. This takes about 20 seconds.

---

## The flow

Suggested split: **Bhumika** speaks for steps 1 to 3 (data and AI), **Adeeb** for steps 4 to 6
(safety, forecast, reports). Change this to match who built what.

### Step 1. Login and upload (about 45 seconds)

**Do:** Log in with `demo@biagent.local` / `Demo@12345`. On the Datasets page, choose
`data/indian_retail_sales.csv`, name it `Retail Sales`, click **Upload and clean**.

**Say:** "This is three years of Indian retail orders, about ten thousand rows. We added
real-world mess on purpose. Watch what the cleaning pipeline finds."

**Point at the cleaning summary:**
- 119 duplicate rows removed
- 1,509 dates in other formats standardised
- 517 values with inconsistent capitals fixed
- 389 rows with missing values filled

**Say:** "The clean data is now its own table in PostgreSQL."

### Step 2. Automatic overview (about 40 seconds)

**Do:** Click **View overview**.

**Say:** "Without any question from us, the system picked the KPIs and six charts. No AI is
used here, only Pandas."

**Point at:**
- Monthly Revenue: "You can see the festive spike every October and November, and growth each year."
- Share of Revenue by Region: "East is clearly the weak region."

**Do (optional):** Click the **Data quality** tab for 3 seconds to show the same cleaning summary and the column list.

### Step 3. Ask questions (about 100 seconds)

**Do:** Click **Ask a question**.

**Question 1. Type or click:**
> Which region had the highest revenue last quarter?

**Say:** "The system wrote SQL, checked it, ran it, chose a bar chart and explained it.
West is first, East is last." Click **Show SQL**. "This is the exact query. Notice the
date filter for October to December 2025 and the LIMIT that our safety layer added.
'Last quarter' is measured from the latest date in the data."

**Question 2:**
> Compare revenue and profit by product category

**Say:** "Here is our hidden pattern. Furniture has good revenue but negative profit."

**Question 3:**
> What is the average discount for each product category?

**Say:** "And this explains it. Furniture gets about 33% discount, the others about 7%.
Heavy discounts are destroying the profit. That is a real business insight, found in three questions."

**Question 4 (unclear on purpose):**
> Show me the best one

**Say:** "This question is unclear. Instead of guessing, the system asks what we mean."
**Then type the answer:**
> Which product category has the highest revenue?

### Step 4. Safety (about 40 seconds)

**Question 5:**
> Delete all orders from the East region

**Say:** "Now a harmful request. The query was a DELETE, so our checker blocked it before it
reached the database, and logged it. We parse every query with sqlglot and allow only a
single SELECT on the user's own table. As a second layer, queries run as a database user
that only has read permission."

**Note for live mode:** a real model will often refuse this request or ask a question back
instead of writing a DELETE, so you may see a different message. That is also a safe result.
To show the checker itself reliably, use mock mode for this step, where the mock is built
to return a DELETE on purpose.

**Do (optional, if time allows):** Ask `How many orders are there?` and say "Still 9,996. Nothing was deleted."

**If asked for proof:** show `backend/storage/logs/blocked_queries.log` or the VS Code tab with `sql_safety.py`.

### Step 5. Forecast (about 40 seconds)

**Do:** Click **Forecast**, then **Run forecast**.

**Say:** "We compare three models on the last six months, which the models never saw
during training. Linear regression with a month effect has the lowest error, so it is
chosen and used to forecast January to March 2026. The model name, version and scores are
saved in the Prediction table."

**Point at:** the dashed forecast line, and the highlighted row in the model comparison table.

### Step 6. History and PDF report (about 35 seconds)

**Do:** Click **History**. Open the first region question.

**Say:** "Every answer is saved with its SQL and result. Asking the same question again is
answered from here and costs zero AI requests, which matters on a free tier with 50 requests a day."

**Do:** Click **Download PDF** and open the file.

**Say:** "The report has the question, the insight, the chart, the result table, the SQL,
the dataset name and the time."

### Closing line (10 seconds)

**Say:** "To summarise: the AI writes the query and the explanation, but every number comes
from the database, every query is checked, and every claim is verified. Thank you."

---

## Backup questions (all work in mock mode)

Use these if the examiner asks to see more.

| Question | What it shows |
|---|---|
| Show the monthly revenue trend | Line chart, 36 months, festive spikes |
| Show total revenue by year | Steady yearly growth |
| What are the top 5 products by revenue? | Horizontal bar chart, ranking |
| What is the total revenue? | Single value, KPI card |
| Show revenue by region and year | One line per region. East stays flat |
| What is the share of orders by payment mode? | Pie chart |
| What is the profit margin for each product category? | Furniture is negative |
| Which region generated the highest revenue last quarter, and what products contributed most? | The example from the concept note. Uses a WITH query |

## If the examiner asks to see something specific

| They ask | Show |
|---|---|
| "Show me the API" | http://localhost:8000/docs |
| "Show me the admin role" | Log out, log in as `admin@biagent.local` / `Admin@12345`, open **Admin** |
| "Show me the tests" | In the backend terminal: `pytest` (125 passed) |
| "How accurate is it?" | `python scripts/run_evaluation.py` (prints a score for 20 questions) |
| "Show the safety code" | `backend/app/services/sql_safety.py` |
| "Show the prompt" | `backend/app/services/prompts.py` |
| "Try your own question" | Only in live mode. In mock mode say: "Mock mode answers a fixed list. With the API key in live mode it answers any question." |
