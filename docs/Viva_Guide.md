# Viva Guide: 30 Likely Questions with Short Answers

AI-Powered Business Intelligence Agent

Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project

**How to use this guide.** Both of us should be able to answer every question here, not only
the ones from our own part. Each answer names the file where the code lives, so you can open
it if the examiner asks "show me".

---

## Part A: The big picture

### 1. What does your project do, in one minute?
A user uploads a CSV or Excel file of business data. The system cleans it, loads it into
PostgreSQL and shows an automatic overview. Then the user asks questions in plain English.
An LLM writes one SQL query, our code checks that the query is safe, runs it with a
read-only database user, picks a chart with simple rules, and the LLM explains the result
in 2 to 3 lines. Every answer is saved and can be exported as a PDF. There is also a
3 month sales forecast.

### 2. How is this different from just asking ChatGPT about a spreadsheet?
Three things. First, the numbers never come from the LLM. They come from running SQL on the
real data. Second, every query passes a safety check and runs read-only. Third, we check the
LLM's explanation: if it mentions a number that is not in the query result, we throw the
explanation away. So the answer is grounded and can be verified with the "Show SQL" button.

### 3. Explain the architecture.
Five layers, the same as in the concept note:
1. **React frontend** (Vite, Plotly): screens for login, datasets, overview, ask, history, forecast, reports.
2. **FastAPI backend**: login, validation and the API endpoints (`backend/app/routers`).
3. **Agent / orchestrator** (`ask_engine.py`): decides the steps for one question.
4. **Analytics engine**: Pandas for cleaning and overview, SQL for questions, scikit-learn for the forecast.
5. **PostgreSQL**: five app tables, plus one table per uploaded dataset.

### 4. Why do you call it an "agent"?
Because it does not just pass text to an LLM. For each question it follows a decision flow:
check the cache, get SQL from the LLM, validate it, run it, retry once with feedback if it
failed, choose a chart, get an explanation, verify the explanation, save everything. It also
decides when to ask a clarifying question and when to block a request.

### 5. Walk me through what happens when I ask "Which region had the highest revenue last quarter?"
1. The frontend sends the question and dataset id to `POST /api/ask`.
2. The backend checks the user owns that dataset.
3. Cache check: was this exact question asked on this dataset before? If yes, return the saved answer.
4. LLM call 1: we send the question, the table schema and the dates for "last quarter". It returns JSON with one SQL query.
5. `sql_safety.py` parses the SQL and checks it. A row limit is added.
6. `query_runner.py` runs it as the read-only user with a 10 second timeout.
7. `chart_selector.py` sees one text column and one number column, so it picks a bar chart.
8. LLM call 2: we send the question and the result rows. It returns 2 to 3 sentences.
9. `insight.py` checks every number in those sentences against the result.
10. The answer is saved in Analysis_History and returned to the frontend.

---

## Part B: AI and LLM

### 6. Which LLM do you use and how do you call it?
We use OpenRouter, a service that gives one API for many models. Its API is compatible with
OpenAI's: we send a POST request to `/chat/completions` with a list of messages. The default
model is a free NVIDIA Nemotron model. The model name and API key are in the `.env` file,
so we can change the model without touching code. The code is in `llm_client.py`.

### 7. What is in your prompt for writing SQL?
The system prompt (`prompts.py`) contains: the rules (one SELECT only, only this table, only
these columns, give clear names to calculated columns), the table schema with column types
and example values, three sample rows, and the exact dates that "last quarter" and
"last month" mean. It asks for a JSON reply with either `"action": "sql"` or
`"action": "clarify"`.

### 8. What data do you send to the LLM? Is the user's data safe?
We send only the table structure, a few example values, three sample rows, and later the
result of the query (at most 30 rows). We never send the full dataset. The explanation call
gets only the question and the result, not even the schema.

### 9. The model does not support JSON mode. How do you get reliable JSON?
We ask for JSON in the prompt, then parse defensively in `json_parsing.py`: remove code
fences, find the first balanced `{ ... }` block (taking care of braces inside strings), and
load it. If that fails, we ask the model once more and tell it the reply was not valid JSON.

### 10. What is hallucination and how do you stop it?
Hallucination is when an LLM states something that sounds right but is made up. We stop it in
three ways. The LLM never computes numbers: SQL does. The explanation prompt forbids new
calculations. And after the LLM replies, `numbers_are_grounded()` in `insight.py` extracts
every number from its text and checks it against the result. If any number is not found,
the text is dropped and a rule-based summary is shown instead.

### 11. Give an example of an insight that would be rejected.
If the result has West = 2,48,43,883 and East = 77,84,979, and the LLM writes
"West earned 3.2 times as much as East", the number 3.2 is not in the result (the LLM
calculated it), so the insight is rejected. "West leads with 2.48 crore" is accepted,
because 2.48 crore is the result value rounded.

### 12. How do you handle the free tier limits (20 per minute, 50 per day)?
- At most 2 LLM calls per question, plus one retry.
- Chart selection uses rules, so it costs zero calls.
- The same question on the same dataset is answered from history with zero calls.
- The app counts its own requests and shows a friendly message before the limit is hit.
- Mock mode needs no calls at all.

### 13. What happens when OpenRouter is down or busy?
`llm_client.py` retries with backoff (waits 2 seconds, then 5). If the main model still
fails and `LLM_FALLBACK_MODEL` is set, it tries that model. If everything fails, the user
sees a clear message, not a crash. If only the explanation call fails, the answer is still
shown with an automatic summary.

### 14. What is mock mode and why did you build it?
With `LLM_MODE=mock`, a small Python file (`mock_llm.py`) plays the role of the LLM for a
fixed list of questions about the sample dataset. It returns a JSON reply just like a real
model, and that reply goes through the same safety check, database and chart code. We built
it to test the app without a key and to keep the live demo safe if the internet or the
free model fails. The numbers are still real, because the SQL is really executed.

### 15. When does the system ask a clarifying question?
When the question does not say what to measure or could mean very different things, for
example "Show me the best one". The prompt tells the LLM to reply with
`"action": "clarify"` instead of guessing. The user's next message is sent together with
the first question, so the LLM has the full context.

---

## Part C: SQL safety and security

### 16. An LLM could write `DROP TABLE`. How do you prevent damage?
Two independent layers.
**Layer 1, the checker** (`sql_safety.py`): parses the query with sqlglot and allows it
only if it is a single SELECT, on the user's own dataset table, using columns that exist,
with safe functions. A row limit is added.
**Layer 2, the database**: the query runs as a separate PostgreSQL user that only has
SELECT permission on dataset tables, in a read-only transaction, with a 10 second timeout.
Even if layer 1 had a bug, layer 2 would refuse.

### 17. Why parse the SQL? Why not just search for words like DELETE?
Searching text is easy to trick and gives false alarms. A harmful statement can hide inside
a `WITH` clause, and a harmless column might be called `update_date`. sqlglot turns the
query into a tree of typed nodes, so we can ask exact questions: "is the root a Select
node?", "is there any Delete node anywhere?", "which tables are read?".

### 18. Can one user read another user's data?
No. The API only accepts a `dataset_id` that belongs to the logged-in user (`deps.py`). The
checker then allows only that dataset's table. A query naming any other table, including
another user's dataset table or the `users` table, is blocked. The read-only database user
also cannot read the `users` table at all.

### 19. How does login work?
Passwords are hashed with bcrypt, so the real password is never stored. After login the
backend creates a JWT token that contains the user id, the role and an expiry time, signed
with a secret key from `.env`. The frontend sends this token in the `Authorization` header
with every request. `get_current_user` in `security.py` verifies it. There are two roles:
user and admin. Admin-only endpoints use the `require_admin` dependency.

### 20. Where are your secrets stored?
Only in the `.env` file, which is listed in `.gitignore`. The API key, database passwords
and JWT secret are never in the code. `make_env.py` generates random database passwords and
a random JWT secret.

---

## Part D: Data and analytics

### 21. What does your cleaning pipeline do?
Seven steps in a fixed order (`cleaning.py`):
1. Clean column names (lower case with underscores).
2. Trim spaces and treat "", "NA", "null" as missing.
3. Remove empty rows and columns.
4. Fix types: numbers stored as text become numbers, mixed date formats become dates.
5. Fix inconsistent capitals ("north", "NORTH" become "North").
6. Remove duplicate rows.
7. Fill missing values: median for numbers, "Unknown" for text.
The user sees a summary with the number of rows affected by each step.

### 22. Why median and not mean for missing numbers?
The mean is pulled by extreme values. In sales data a few very large orders would make the
mean too high. The median is the middle value, so it is a safer "typical" number.

### 23. Tell me about your sample dataset.
About 10,000 retail orders across 2023 to 2025, in INR, generated by
`data/generate_dataset.py` with a fixed random seed so it is always the same. We built in
real patterns: festive spikes in October and November, steady yearly growth, a weak region
(East), and a category where heavy discounts cause a loss (Furniture). We also added mess
on purpose (duplicates, missing values, mixed date formats, odd capitals) so the cleaning
step has something to fix.

### 24. How is the chart chosen?
With simple rules based on the shape of the result (`chart_selector.py`): one row gives KPI
cards, a time column with numbers gives a line chart, one category with a number gives a
bar chart, a "share" question with few rows gives a pie chart, two categories with a number
give grouped bars, only numbers give a scatter chart, anything else is shown as a table.
No LLM is used, so it is free and consistent.

### 25. Explain your forecasting. How did you choose the model?
We add up revenue per month and compare three approaches: a 3 month moving average,
seasonal naive (same month last year), and linear regression with a trend and a month
effect. We hold out the last 6 months as a test period, fit each model only on the earlier
months, and measure MAE and RMSE on the test months. The model with the lowest RMSE wins,
is fitted again on all the data, and forecasts the next 3 months. On our data linear
regression wins because it captures both the growth and the festive season.

### 26. What are MAE and RMSE? What is data leakage and how did you avoid it?
MAE is the average size of the error. RMSE squares the errors before averaging and then
takes the square root, so big misses count more. Data leakage means the model sees
information from the future during training, which makes the test score look better than
it really is. We avoid it by splitting by time, fitting only on the months before the test
period, and using only inputs known in advance (the month number and calendar month).
A test in `tests/test_ai_helpers.py` proves it: changing the test months does not change
the predictions.

### 27. How did you test the accuracy of the whole system?
We wrote 20 business questions and computed the correct answers directly in Pandas
(`evaluation/questions.py`). The script `run_evaluation.py` sends each question through the
real API and compares the result with the Pandas answer. It prints an accuracy score. We
also have 125 pytest tests for the SQL checker, the cleaning pipeline, the insight check,
chart selection and forecasting.

---

## Part E: Backend, database and frontend

### 28. Why FastAPI? What are your main endpoints?
FastAPI is fast to write, validates request data with Pydantic, and creates interactive
API documentation at `/docs` automatically. Main endpoints:
`/api/auth` (signup, login), `/api/datasets` (upload, list, overview, preview),
`/api/ask` (questions), `/api/history`, `/api/forecast`, `/api/reports` (create and
download PDFs) and `/api/admin` (all users and datasets).

### 29. Describe your database design.
Five tables from the concept note: **User**, **Dataset**, **Analysis_History**,
**Prediction** and **Report**. A user has many datasets. A dataset has many analyses.
An analysis can have predictions (for forecasts) and reports (PDFs). Each uploaded file is
also stored as its own table in a separate schema called `dataset_tables`. We keep that
schema separate so the read-only user can be given access to it and nothing else.

### 30. How does the frontend talk to the backend, and how are charts drawn?
The React app calls the backend with `fetch` through one helper (`api.js`) that adds the
login token and turns errors into readable messages. In development Vite forwards `/api`
requests to the backend on port 8000. The backend sends a chart description (type, x
values, series). `ChartView.jsx` turns that into a Plotly chart. The same description is
drawn with Matplotlib for the PDF, so the screen and the report always match.

---

## Quick facts to remember

| Item | Value |
|---|---|
| LLM calls per question | 2, plus at most 1 retry |
| Free tier limits | about 20 per minute, 50 per day |
| Row limit on queries | 1000 |
| Query timeout | 10 seconds |
| Sample dataset | 9,996 orders, Jan 2023 to Dec 2025, total revenue about 7.56 crore |
| Weak region | East |
| Loss-making category | Furniture (average discount about 33%) |
| Best forecast model on sample data | Linear regression (trend + month effect) |
| Tests | 125 pytest tests, 32 smoke checks, 20 evaluation questions |
| Password hashing | bcrypt |
| Token | JWT, HS256, 8 hours |

## Honest limitations (say these before the examiner finds them)

- One question works on one table. No joins across datasets.
- A free LLM can still write SQL that is valid but answers a slightly different question. The "Show SQL" button lets the user check.
- The insight check verifies numbers, not words. A wrong adjective ("strong growth") could pass.
- The forecast uses simple models on monthly totals. It is an estimate, not a guarantee.
- Mock mode only knows the sample dataset.
