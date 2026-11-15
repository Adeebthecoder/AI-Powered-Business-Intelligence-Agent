# Design Decisions

This file lists every choice that the concept note did not specify, and the reason for it.
It is useful in the viva when someone asks "why did you do it this way?".

Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project

---

## 1. Scope

| # | Decision | Why |
|---|---|---|
| 1.1 | Everything in the "Future Scope" section of the concept note is left out: joins across datasets, live database connectors, scheduled refresh, anomaly detection, explainable AI, PowerPoint export, voice queries, enterprise audit logs. | Kept the project achievable and every included part fully working. |
| 1.2 | PDF export of a single analysis IS included, even though "automated PDF/PowerPoint executive reports" is in Future Scope. | The project brief asked for it. Our PDF is one analysis exported on request. The future scope item means automatic multi-page executive reports, which we did not build. |
| 1.3 | A simple 3 month forecast IS included, even though "advanced forecasting" is in Future Scope. | The brief asked for it. We use three simple, explainable models, not advanced ones. |
| 1.4 | One question works on one dataset table only. No joins. | Multi-dataset reasoning is Future Scope. It also makes the safety rule very simple: "only the user's own table". |
| 1.5 | Only PostgreSQL is supported (the concept note says PostgreSQL/MySQL). | One database keeps the SQL dialect, the safety parser and the read-only role consistent. |
| 1.6 | Clustering, classification and anomaly detection (listed as "candidate techniques") are not built. | The concept note says ML is optional and should not be forced onto the data. Forecasting is the technique that fits sales data. |

## 2. LLM usage

| # | Decision | Why |
|---|---|---|
| 2.1 | Two LLM calls per question: (1) write SQL, (2) explain the result. Chart choice uses rules, not the LLM. | The free tier allows about 50 requests per day. Rules are free, instant and give the same chart every time. |
| 2.2 | One shared retry for the SQL step. The retry is used if the reply is not valid JSON, or the SQL has a fixable mistake (unknown column, PostgreSQL error). So the maximum is 3 calls per question. | Keeps the promise "2 calls plus one retry". The retry message tells the model exactly what was wrong. |
| 2.3 | Destructive SQL (DELETE, DROP, other tables) is blocked at once with no retry. | A retry would waste a request and would invite the model to "try again" at something we never want. |
| 2.4 | The insight call asks for plain text, not JSON. | Nothing to parse, so nothing to fail, and no retry is needed for it. |
| 2.5 | We call OpenRouter with the `httpx` library directly instead of the `openai` Python package. | The API is one HTTP POST. Doing it ourselves keeps retry, backoff, fallback and rate limit handling visible in one short file that we can explain. |
| 2.6 | The app counts its own requests (per minute in memory, per day in `backend/storage/llm_usage.json`) and stops before OpenRouter does. | Gives a friendly message instead of an error from the provider, and the Ask page can show "requests used today". The daily count uses UTC because OpenRouter resets at midnight UTC. |
| 2.7 | Each LLM call tries the main model up to 2 times (waiting 2 s, then 5 s), then `LLM_FALLBACK_MODEL` if set. Each try counts as one request. | Free endpoints are sometimes busy. Two tries is enough to ride out a short hiccup without burning the daily budget. |
| 2.8 | If the insight call fails (busy model or rate limit), the answer is still returned with a rule-based summary. | The data, chart and SQL are already correct. Only the wording is missing, so the user should not lose the answer. |
| 2.9 | Temperature is 0. | We want the same SQL for the same question, not creativity. |
| 2.10 | The cache is the Analysis_History table itself. Same dataset + same question (ignoring capitals and punctuation) returns the saved answer with 0 calls. | No extra table needed. The answer shows a "Saved answer" label so the user knows. |
| 2.11 | Only successful answers are cached. Errors and clarifications are not. | A failure caused by a busy model should not be remembered forever. |

## 3. What is sent to the LLM

| # | Decision | Why |
|---|---|---|
| 3.1 | Call 1 gets: table name, column names and types, min and max of number and date columns, 3 example values per column, 3 sample rows. | The minimum needed to write correct SQL. |
| 3.2 | For text columns with 15 or fewer different values, the full list of values is sent (for example the four region names). | Without it the model writes `region = 'north'` and gets no rows. These are category labels, not customer data. This is the one place we go slightly beyond "a few sample rows", so we note it here. |
| 3.3 | Call 2 gets only the question and the result rows (at most 30 rows). It does not get the schema or the SQL. | The model can only talk about what the query actually returned. |
| 3.4 | The full dataset is never sent. | Privacy, and it would not fit anyway. |

## 4. Meaning of "last quarter"

| # | Decision | Why |
|---|---|---|
| 4.1 | Time words ("last quarter", "last month", "this year") are measured from the **latest date in the data**, not from today's date. | The sample data ends in December 2025. Measured from today, "last quarter" would have no data and every demo answer would be empty. |
| 4.2 | "Last quarter" means the most recent **complete** calendar quarter in the data. For the sample data that is October to December 2025. | A half-finished quarter would look like a fall in sales. |
| 4.3 | The backend works these dates out in Python and gives them to the LLM in the prompt. | Date arithmetic is something LLMs get wrong. Code does not. |

## 5. SQL safety

| # | Decision | Why |
|---|---|---|
| 5.1 | Queries are parsed into a tree with `sqlglot` and the tree is checked. We do not search the text for bad words. | Text matching is easy to trick (comments, odd spacing, a column called "update_date"). |
| 5.2 | Only a single SELECT is allowed. WITH (CTE) and subqueries are allowed. UNION is not. | CTEs and subqueries are needed for real questions. UNION is not needed for one table and is a classic way to pull data from another table. |
| 5.3 | Functions that sqlglot does not recognise must be on a short allow list. | Blocks `pg_sleep`, `pg_read_file`, `dblink`, `set_config` and anything else we did not think of. An allow list is safer than a block list. |
| 5.4 | The query must read the dataset table. `SELECT version()` is blocked. | Questions are about the data, not about the server. |
| 5.5 | A row limit is always added (default 1000, `SQL_MAX_ROWS`). A higher limit is lowered. | Protects the browser and the LLM from huge results. |
| 5.6 | The checker always rewrites the table name to `"dataset_tables"."<table>"`. | Removes any doubt about which schema is read. |
| 5.7 | Second layer: queries run as a separate PostgreSQL user (`bi_readonly`) that only has SELECT on the `dataset_tables` schema, with a read-only transaction and a 10 second timeout. | "Defence in depth". Even if the checker had a bug, the database itself would refuse to change or leak anything. This user cannot read the users table. |
| 5.8 | Uploaded data lives in its own schema (`dataset_tables`), separate from the app tables (`public`). | Makes the read-only permission a single clean rule. |
| 5.9 | Blocked queries are written to `backend/storage/logs/blocked_queries.log` and also saved in history with status "blocked". | The brief says "block everything else and log it". The file is for review, the history row is for the user. |
| 5.10 | Access control between users is done in the API (a user can only name their own `dataset_id`), not with one database role per user. | One role per user would be heavy for a minor project. The checker only ever allows the one table that belongs to the dataset the API already authorised. |

## 6. Insight checking

| # | Decision | Why |
|---|---|---|
| 6.1 | After the LLM writes the insight, every number in it is checked against the result. If one number is not found, the whole insight is dropped. | The concept note's main principle: the AI must not invent values. |
| 6.2 | When an insight is dropped, a rule-based summary is shown instead, with a note saying so. | The brief says "drop the insight". Showing nothing would look broken, and the rule-based text uses only result values, so it is always safe. |
| 6.3 | A number passes if it is a result value (rounding allowed), a result value written in thousand, lakh, crore or million, a fraction written as a percentage, a number from the user's question, a number inside a text cell (like the 2025 in a date), or a count up to the number of rows (max 10). | Covers honest ways of writing a number. Anything the LLM calculated itself (a difference, a ratio, a share) fails, which is what we want. |
| 6.4 | Numbers glued to letters ("5G", "Q4", "128GB") are not treated as numbers. | They are part of names, not claims. |

## 7. Mock mode

| # | Decision | Why |
|---|---|---|
| 7.1 | The mock returns a JSON reply inside a code fence, like a real model. It then goes through the same parser, safety check, read-only user and chart rules. | Mock mode tests the real pipeline. Only the "thinking" is faked. Numbers always come from running SQL. |
| 7.2 | Mock mode knows 25 questions for the sample dataset (plus the trap in 7.3), 3 unclear questions that trigger a clarifying question, and tolerates small typing differences. | Enough for a full demo and for the 20 question evaluation. |
| 7.3 | One mock question ("Delete all orders from the East region") makes the mock return a DELETE statement on purpose. | Lets us show the safety checker working in the demo. A real model would usually refuse, so this is the only reliable way to show it live. |
| 7.4 | In mock mode the insight is the rule-based summary. | No API, no text generation. |
| 7.5 | For other datasets, mock mode says it only knows the sample dataset. | Honest. It does not pretend. |

## 8. Data pipeline

| # | Decision | Why |
|---|---|---|
| 8.1 | Cleaning steps run in a fixed order and use no randomness. | Reproducible: same file, same result. |
| 8.2 | Missing numbers are filled with the column median. Missing text becomes "Unknown". Missing dates are left empty. | Median is not pulled by extreme values. "Unknown" keeps the row and is visible in charts. A date cannot be guessed. |
| 8.3 | Unclear dates such as 03/04/2024 are read day first (3 April). | Indian date convention. |
| 8.4 | Inconsistent capitals ("north", "NORTH") are changed to the most common spelling in that column. | Works for any dataset without a dictionary. |
| 8.5 | A text column becomes a number if 95% of its values are numbers, a date if 90% parse as dates. The few bad values become missing and are counted. | Tolerates a little mess without converting real text columns. |
| 8.6 | Column names that are SQL keywords get `_col` added ("order" becomes "order_col"). | Avoids broken SQL from the LLM. |
| 8.7 | Upload limit is 20 MB, formats are `.csv` and `.xlsx`. | Enough for a demo. Old `.xls` would need another library. |
| 8.8 | The overview is computed once at upload and stored as JSON with the dataset. | Opening the overview page is instant and needs no recomputation. |
| 8.9 | The overview uses no LLM at all. | It is pure statistics, so it is free and exact. |

## 9. Sample dataset

| # | Decision | Why |
|---|---|---|
| 9.1 | 9,996 orders from January 2023 to December 2025, one product per order, random seed 42. | Three full calendar years make yearly growth and seasonality easy to see. |
| 9.2 | Festive spike: October and November get about 1.6 to 1.75 times the normal orders, plus extra discounts. | Matches Navratri, Dussehra and Diwali. |
| 9.3 | Weak region: East has 13% of orders and no yearly growth. Other regions grow 17% to 20% a year. | Gives a clear "which region is weak" insight. |
| 9.4 | Problem category: Furniture gets 20% to 45% discounts, so it makes a loss overall. | Gives a clear "discounts hurt profit" insight. |
| 9.5 | Mess added on purpose: about 1.2% duplicate rows, 15% of dates in other formats, 2% to 3% odd capitals or spaces in three columns, 0.5% to 1.5% missing values in four columns. | The cleaning summary has real work to show. |
| 9.6 | Product names are generic (no real brands). | Avoids using real company names. |

## 10. Forecasting

| # | Decision | Why |
|---|---|---|
| 10.1 | Three models: moving average (last 3 months), seasonal naive (same month last year), linear regression with trend and month effect (scikit-learn). | The brief asks for at least two. Two simple baselines make the comparison meaningful, and all three are easy to explain. |
| 10.2 | The last 6 months are the test period (3 if there are fewer than 30 months). The winner is the model with the lowest RMSE. | A time-based split is the correct way to test a forecast. RMSE punishes big misses, which matter most in sales planning. |
| 10.3 | No leakage: models are fitted only on months before the test period. The only inputs are the month counter and the calendar month. There is a pytest test that proves changing the test months does not change the predictions. | Required by the brief and the concept note. |
| 10.4 | After choosing, the winner is fitted again on all months to forecast the next 3. | Standard practice: test on held-out data, then use all data for the real forecast. |
| 10.5 | An unfinished last month is dropped. At least 15 full months are needed. | Half a month looks like a crash. Fewer months cannot show a yearly pattern. |
| 10.6 | Model version is "1.0 (data up to Dec 2025)". | Records both the code version and what data it was trained on. |

## 11. Database

| # | Decision | Why |
|---|---|---|
| 11.1 | The five tables from section 11 of the concept note are used. Extra fields: `Dataset.table_name`, `cleaning_summary`, `overview`, `row_count`, `column_count`, `user_id`; `Analysis_History.sql_query`, `status`, `result_data`, `chart_spec`, `insight_source`, `model_used`, `llm_calls`, `question_key`, `error_message`; `Report.file_path`; `created_at` on Prediction. | Needed for the cache, the history page, PDF export and reproducibility. |
| 11.2 | A forecast creates one Analysis_History row and one Prediction row linked to it. | Matches the concept note (Prediction has `analysis_id`) and lets forecasts appear in History and be exported like any answer. |
| 11.3 | Tables are created at startup with SQLAlchemy `create_all`. No migration tool. | Simple for a project whose schema does not change after release. |
| 11.4 | PDF files are saved in `backend/storage/reports/`. The Report table stores the title, the text content and the file name. | Files on disk are simpler than binary data in the database. |

## 12. Login and roles

| # | Decision | Why |
|---|---|---|
| 12.1 | Passwords are hashed with bcrypt. Tokens are JWT (HS256) and last 8 hours. | Standard, well understood choices. 8 hours covers a working session. |
| 12.2 | Signup always creates a normal user. The admin account is created from the `.env` file. | Nobody can make themselves admin from the signup form. |
| 12.3 | The demo and admin logins are settings in `.env` (with demo values in `.env.example`), not in the code. | The brief asks for no hardcoded passwords and also for a stated demo login. Settings satisfy both. They can be changed before the first start. |
| 12.4 | Database passwords and the JWT secret are generated randomly by `make_env.py`. | No default secrets exist anywhere. |
| 12.5 | One `.env` file in the project folder is shared by the backend and docker-compose. | One place for all settings. |
| 12.6 | The token is stored in the browser's localStorage. | Simple and fine for a local demo app. |

## 13. Frontend

| # | Decision | Why |
|---|---|---|
| 13.1 | Plain CSS in one file, no UI framework. Accent colour indigo (#4338CA). System fonts. | Easy to read and explain. System fonts mean the app looks right without internet. |
| 13.2 | Plotly is used directly through a small wrapper component (`ChartView.jsx`) instead of the `react-plotly.js` package. | One less dependency, and the code shows exactly how a chart is drawn. |
| 13.3 | The backend sends one chart description format for every chart. The frontend draws it with Plotly and the PDF draws it with Matplotlib. | One source of truth: the chart in the PDF always matches the screen. |
| 13.4 | Charts with several series use extra colours. Single series charts use only the accent colour. | Several lines in one colour cannot be told apart. |
| 13.5 | Numbers use Indian digit grouping (12,34,567) and Cr / L on KPI cards. | The data is in INR. |
| 13.6 | The Vite dev server passes `/api` requests to the backend (proxy). | The frontend never needs the backend address and there are no CORS problems in development. |
| 13.7 | The Ask page keeps the chat in memory until logout. History is the permanent record. | Simple. Nothing is lost because every answer is already in the database. |

## 14. Evaluation

| # | Decision | Why |
|---|---|---|
| 14.1 | The 20 correct answers are computed in Pandas on the cleaned data, with no SQL. | An independent second method. If SQL and Pandas agree, the answer is very likely right. |
| 14.2 | The evaluation sends questions through the real `/api/ask` endpoint. | It tests the same path a user takes. |
| 14.3 | An answer is correct if the expected name or number appears in the result, within 0.5%. For rates, 0.33 and 33% both count. | The LLM may round or add extra columns. That should not count as wrong. |
| 14.4 | In mock mode the score checks the pipeline only, and the script says so. | Honest reporting: mock SQL was written by us, so 100% there says nothing about the AI model. |
| 14.5 | In live mode the script waits 7 seconds between questions and reuses saved answers. | Stays under 20 requests per minute and does not waste the daily limit. |
