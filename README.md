# AI-Powered Business Intelligence Agent

**Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project**

Upload a CSV or Excel file of business data, see an automatic overview, then ask
questions in plain English such as *"Which region had the highest revenue last quarter?"*.
The system writes a safe SQL query, runs it, picks a chart, and explains the result in
2 to 3 lines of simple business language. Every answer is saved to history and can be
exported as a PDF report. There is also a sales forecast page.

---

## Contents

1. [What is in this folder](#1-what-is-in-this-folder)
2. [What you need to install first](#2-what-you-need-to-install-first)
3. [Setup, step by step](#3-setup-step-by-step)
4. [Using the app](#4-using-the-app)
5. [Using the real AI model (OpenRouter)](#5-using-the-real-ai-model-openrouter)
6. [Checking that everything works](#6-checking-that-everything-works)
7. [Starting the app again later](#7-starting-the-app-again-later)
8. [Troubleshooting](#8-troubleshooting)
9. [Where to read more](#9-where-to-read-more)

---

## 1. What is in this folder

```
ai-bi-agent/
  backend/              Python + FastAPI server
    app/                the application code
      routers/          API endpoints (auth, datasets, ask, history, forecast, reports, admin)
      services/         the logic (cleaning, SQL safety, LLM client, charts, forecast, PDF)
    scripts/            setup and test scripts you run from the terminal
    tests/              pytest tests
    evaluation/         20 questions with correct answers computed in Pandas
    requirements.txt    list of Python packages
  frontend/             React + Vite web app
  data/                 sample dataset and the script that generates it
  docs/                 project report, viva guide, demo script
  docker-compose.yml    starts PostgreSQL in Docker (optional)
  .env.example          example settings file
  DECISIONS.md          design choices and the reasons for them
  README.md             this file
```

---

## 2. What you need to install first

You need three programs: **Python**, **Node.js** and **PostgreSQL**.
Install them once. If you already have them, skip to section 3.

### 2.1 Python (version 3.11, 3.12 or 3.13)

> Important: use Python 3.11, 3.12 or 3.13. Very new versions (3.14 and later) may fail
> at the `pip install` step because some packages are not ready for them yet.
> It is fine to have more than one Python version installed.

**Windows**

1. Go to https://www.python.org/downloads/windows/ and download the
   "Windows installer (64-bit)" for Python 3.13.
2. Run it. **Tick the box "Add python.exe to PATH"** on the first screen, then click "Install Now".
3. Open **Command Prompt** (press the Windows key, type `cmd`, press Enter) and check:
   ```
   py -3.13 --version
   ```
   It should print `Python 3.13.x`.

**Mac**

1. Go to https://www.python.org/downloads/macos/ and download the "macOS 64-bit universal2 installer" for Python 3.13.
2. Open the downloaded file and follow the installer.
3. Open **Terminal** (press Cmd + Space, type `Terminal`, press Enter) and check:
   ```
   python3.13 --version
   ```

### 2.2 Node.js (version 20 or newer)

1. Go to https://nodejs.org and download the **LTS** version for your system.
2. Run the installer and accept the default options.
3. Close and reopen your terminal, then check:
   ```
   node --version
   npm --version
   ```

### 2.3 PostgreSQL (version 14 or newer)

Choose **one** of the two ways below. Way A is the simplest for most people.

**Way A: install PostgreSQL directly (recommended)**

*Windows*
1. Go to https://www.postgresql.org/download/windows/ and click "Download the installer".
2. Run it and keep the default options. Keep the port as **5432**.
3. The installer asks for a **password for the user "postgres"**. Choose one and
   **write it down**. You need it once in step 3.4.
4. At the end, untick "Launch Stack Builder" and finish.

*Mac*
1. Go to https://postgresapp.com, download Postgres.app and drag it into Applications.
2. Open it and click "Initialize". PostgreSQL now runs on port 5432.
3. With Postgres.app the "postgres" user has no password. When the setup script
   in step 3.4 asks for a password, just press Enter.

**Way B: use Docker**

1. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and start it.
2. That is all for now. You will start the database in step 3.4.

---

## 3. Setup, step by step

Do these steps once. Every command is typed in a terminal
(**Command Prompt** on Windows, **Terminal** on Mac).

> Windows tip: use **Command Prompt**, not PowerShell. The commands below are written for it.

### 3.1 Unzip and open the folder

Unzip the project. You get a folder called `ai-bi-agent`. Keep it somewhere with a
short path, for example `C:\projects\ai-bi-agent` or `~/projects/ai-bi-agent`.

Open a terminal and go into the **backend** folder:

Windows:
```
cd C:\projects\ai-bi-agent\backend
```
Mac:
```
cd ~/projects/ai-bi-agent/backend
```

### 3.2 Create the Python environment and install packages

A "virtual environment" keeps this project's packages separate from the rest of your laptop.

Windows:
```
py -3.13 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
Mac:
```
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

After the second command your terminal line starts with `(venv)`. That means the
environment is active. The install takes a few minutes.

### 3.3 Create the settings file

```
python scripts/make_env.py
```

This creates a file called `.env` in the `ai-bi-agent` folder. It holds all settings.
The script fills in strong random passwords for you, so no password is written in the code.
The app starts in **mock mode**, which needs no API key (see section 5 for the real AI).

### 3.4 Set up the database

**If you chose Way A (PostgreSQL installed):** PostgreSQL is already running. Go straight to the command below.

**If you chose Way B (Docker):** start the database first. Open a **second** terminal in the
`ai-bi-agent` folder (not `backend`) and run:
```
docker compose up -d
```
> If you have PostgreSQL installed **and** use Docker, both want port 5432. In that case open
> `.env` in a text editor, change `DB_PORT=5432` to `DB_PORT=5433`, save, and run the command again.

**Then, for both ways,** go back to the first terminal (the one that shows `(venv)`) and run:
```
python scripts/setup_database.py
```

- Way A on Windows: it asks for the **postgres password** you chose when installing PostgreSQL. Type it and press Enter. Nothing shows while you type. That is normal.
- Way A on Mac with Postgres.app: if it asks for a password, press Enter.
- Way B: it does not ask anything.

It should end with: `Database setup finished. You can now start the backend.`

### 3.5 Start the backend

In the same terminal (still in `backend`, still showing `(venv)`):
```
uvicorn app.main:app --reload
```

Leave this terminal open. When you see `Application startup complete`, open
http://localhost:8000/docs in a browser. You should see the list of all API endpoints.

### 3.6 Start the frontend

Open a **new** terminal (keep the backend one running) and go to the **frontend** folder:

Windows:
```
cd C:\projects\ai-bi-agent\frontend
npm install
npm run dev
```
Mac:
```
cd ~/projects/ai-bi-agent/frontend
npm install
npm run dev
```

`npm install` is only needed the first time. When you see `Local: http://localhost:5173/`,
open http://localhost:5173 in a browser.

### 3.7 Log in

Two accounts are created automatically the first time the backend starts:

| Account | Email | Password | Can do |
|---|---|---|---|
| Demo user | `demo@biagent.local` | `Demo@12345` | Upload data, ask questions, forecast, reports |
| Admin | `admin@biagent.local` | `Admin@12345` | Everything above, plus see all users and all datasets |

These logins come from the `.env` file (`DEMO_USER_PASSWORD` and `ADMIN_PASSWORD`).
They are demo logins for the presentation. If you want different ones, change them in
`.env` **before** the first start of the backend. You can also create your own account
with the "Sign up" tab.

---

## 4. Using the app

1. **Datasets**: click the upload box and choose `data/indian_retail_sales.csv` from the
   project folder. Click "Upload and clean". You see a cleaning summary: what was fixed
   and how many rows were affected.
2. **Overview**: KPI cards, six automatic charts, data quality, statistics and a preview.
3. **Ask**: click a suggested question or type your own. Each answer has an insight,
   a chart, the result table, a "Show SQL" button and a "Download PDF" button.
4. **History**: every question and forecast, with its result. Click a row to open it.
5. **Forecast**: click "Run forecast". Three models are compared on held-out months and the best one forecasts the next 3 months.
6. **Reports**: every PDF you created, ready to download again.
7. **Admin** (admin login only): all users and all datasets.

**Mock mode and live mode.** The small label at the bottom left shows the AI mode.
- **mock**: answers a fixed list of demo questions with no API call. Click "Show all demo questions" on the Ask page to see them. Use this for testing and as a safety net in the demo.
- **live**: sends your question to the real AI model, so you can ask anything. See the next section.

---

## 5. Using the real AI model (OpenRouter)

### 5.1 Get a free API key

1. Go to https://openrouter.ai and click "Sign in". Create an account (Google or email).
2. Open https://openrouter.ai/keys (or click your profile picture, then "Keys").
3. Click **Create Key**, give it any name, and click Create.
4. **Copy the key now.** It starts with `sk-or-`. It is shown only once.
5. Free models need one privacy setting. Open https://openrouter.ai/settings/privacy and
   turn on the option that allows **free endpoints** (free models may use prompts to
   improve the model). Without it, free models answer "No endpoints found".

### 5.2 Put the key in the settings file

1. Open the file `.env` in the `ai-bi-agent` folder with a text editor (Notepad or TextEdit).
2. Change these two lines:
   ```
   LLM_MODE=live
   OPENROUTER_API_KEY=sk-or-paste-your-key-here
   ```
3. Save the file.
4. Restart the backend: go to its terminal, press `Ctrl + C`, then run `uvicorn app.main:app --reload` again.

The label at the bottom left of the app now says **AI mode: live**.

> Never share the `.env` file and never upload it to GitHub. The `.gitignore` file already keeps it out of Git.

### 5.3 Things to know about the free tier

- About **20 requests per minute** and **50 per day**. One question uses 2 requests
  (one to write SQL, one to explain the result), sometimes 3. So plan for about 20 new questions per day.
- The **same question on the same dataset costs nothing** the second time. It is answered from history.
  Tip: ask your demo questions once the day before, so they are saved.
- The counter on the Ask page shows how many requests you used today. It resets at 5:30 am IST.
- The free model is sometimes busy. The app retries by itself. If you set
  `LLM_FALLBACK_MODEL` in `.env` to another free model from https://openrouter.ai/models
  (filter by "free"), it is tried when the main model fails.
- If the limit is reached during your demo, set `LLM_MODE=mock`, restart the backend, and continue.
- Only the table structure, three sample rows and the query result are sent to the AI. The full dataset never leaves your laptop.

---

## 6. Checking that everything works

Run these from the `backend` folder with the environment active (`(venv)` showing).

**Unit tests** (no database needed):
```
pytest
```
Expected: `125 passed`.

**Full flow test** (backend must be running in another terminal, in mock mode):
```
python scripts/smoke_test.py
```
It logs in, uploads the sample file, checks the overview, asks questions, checks that a
harmful query is blocked, runs a forecast and downloads a PDF. Expected: `All 32 checks passed.`

**Evaluation on 20 questions** (backend must be running):
```
python scripts/run_evaluation.py
```
It prints CORRECT or WRONG for each question and an accuracy score.
In mock mode this checks the pipeline. In live mode it measures the real AI model and uses
about 40 of the 50 free daily requests, so run it once, on a day you are not giving a demo.
Use `python scripts/run_evaluation.py --limit 5` for a quick, cheap check.

**Build the frontend** (from the `frontend` folder):
```
npm run build
```

**Make the sample dataset again** (optional, from the `data` folder):
```
python generate_dataset.py
```
It uses a fixed random seed, so it always creates the same file.

---

## 7. Starting the app again later

After the first setup, starting the app takes two terminals.

Terminal 1 (backend):

Windows:
```
cd C:\projects\ai-bi-agent\backend
venv\Scripts\activate
uvicorn app.main:app --reload
```
Mac:
```
cd ~/projects/ai-bi-agent/backend
source venv/bin/activate
uvicorn app.main:app --reload
```

Terminal 2 (frontend):
```
cd C:\projects\ai-bi-agent\frontend      (Mac: cd ~/projects/ai-bi-agent/frontend)
npm run dev
```

Then open http://localhost:5173. If you use Docker for the database, run
`docker compose up -d` in the `ai-bi-agent` folder first. To stop a server, press `Ctrl + C` in its terminal.

---

## 8. Troubleshooting

| Problem | What to do |
|---|---|
| `'py' is not recognized` or `python: command not found` | Python is not installed or not on PATH. Reinstall it and tick "Add python.exe to PATH". On Mac use `python3.13`. |
| `pip install` fails with a long error about building a package | You are probably on a Python version that is too new. Check with `python --version` inside the venv. Delete the `venv` folder and create it again with Python 3.13 (`py -3.13 -m venv venv`). |
| `venv\Scripts\activate` says "running scripts is disabled" | You are in PowerShell. Use Command Prompt instead (Windows key, type `cmd`). |
| `Could not load settings from the .env file` | Run `python scripts/make_env.py` from the `backend` folder. |
| `Could not reach PostgreSQL` or `Could not connect to PostgreSQL` | PostgreSQL is not running or the port is wrong. Windows: open "Services", find "postgresql", click Start. Mac: open Postgres.app. Docker: run `docker compose up -d`. Check `DB_PORT` in `.env`. |
| Setup script says the password was wrong three times | It needs the password of the "postgres" user that you chose when installing PostgreSQL. If you forgot it, the easiest fix is Way B (Docker) with `DB_PORT=5433` in `.env`. |
| `password authentication failed for user "bi_app"` when starting the backend | The `.env` passwords and the database are out of step (for example you made a new `.env`). Run `python scripts/setup_database.py` again. It resets the two app users to the current `.env` passwords. |
| `docker compose up` says "port is already allocated" | PostgreSQL is already using port 5432. Set `DB_PORT=5433` in `.env` and run it again. |
| `docker compose up` says it cannot connect to the Docker daemon | Docker Desktop is not running. Start it and wait until it says "running". |
| `Address already in use` or `port 8000 is in use` | Another program uses the port. Close the old backend terminal, or start on another port: `uvicorn app.main:app --reload --port 8001` and change the port in `frontend/vite.config.js` to match. |
| The website says "Cannot reach the backend" | The backend terminal is not running. Start it (section 7). |
| Login says "Wrong email or password" for the demo user | Use exactly `demo@biagent.local` and `Demo@12345`. If you changed `.env` after the first start, the old password is still stored. Use "Sign up" to make a new account. |
| Ask page says "Mock mode can only answer its fixed list of demo questions" | That is mock mode working as designed. Click a suggested question, or switch to live mode (section 5). |
| "OpenRouter rejected the API key" | The key in `.env` is wrong or has spaces around it. Copy it again. Restart the backend after saving. |
| "The AI model is not available right now" | The free model is busy, the model name is wrong, or the privacy setting in step 5.1 is off. Wait a minute and retry, check `LLM_MODEL` in `.env`, or set `LLM_FALLBACK_MODEL`. Mock mode always works. |
| "Today's free AI limit has been used up" | You reached 50 requests. Saved answers still work. Use mock mode until 5:30 am IST. |
| `npm install` prints warnings about "install scripts" or "deprecated" | Warnings are fine. Only lines starting with `npm error` are real problems. |
| `npm run dev` fails with errors about very long file paths (Windows) | Move the project to a short path such as `C:\projects\ai-bi-agent` and run `npm install` again. |
| Changed `.env` but nothing changed in the app | The backend reads `.env` only when it starts. Stop it with `Ctrl + C` and start it again. |
| Upload fails with "Could not read the file" | The file must be `.csv` or `.xlsx`, with column names in the first row. Old `.xls` files must be saved as `.xlsx` first. |
| You want a completely fresh start | Stop the backend. Delete `.env` and the `backend/storage` folder. In pgAdmin or psql run `DROP DATABASE bi_agent;` (Docker: `docker compose down -v`). Then repeat steps 3.3 to 3.5. |

---

## 9. Where to read more

- `docs/Project_Report.docx`: the full project report draft.
- `docs/Viva_Guide.md`: 30 likely viva questions with short answers.
- `docs/Demo_Script.md`: a 5 minute demo flow with the exact questions to ask.
- `DECISIONS.md`: every design choice that the concept note left open, and why.
- http://localhost:8000/docs: live API documentation (when the backend is running).

---

Developed by Bhumika Panwar and Mohd. Adeeb Siddiqui, MCA 3rd Semester Minor Project
