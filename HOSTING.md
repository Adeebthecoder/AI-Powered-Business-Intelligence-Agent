# How this project is hosted (free plans)

| Part | Host | Settings |
|---|---|---|
| Database | Neon (PostgreSQL) | One project. The app creates the read-only user by itself on every start. |
| Backend | Render, free web service | Root directory `backend`. Build: `pip install -r requirements.txt`. Start: `python scripts/setup_database.py --hosted && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Frontend | Vercel, Hobby plan | Root directory `frontend`, Vite preset. `frontend/vercel.json` makes page refresh work. |

## Environment variables (names only, never commit values)

**Render (backend):** `PYTHON_VERSION`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_APP_USER`,
`DB_APP_PASSWORD`, `DB_READONLY_USER`, `DB_READONLY_PASSWORD`, `JWT_SECRET`,
`DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `LLM_MODE`,
`LLM_MODEL`, `OPENROUTER_API_KEY`, `FRONTEND_ORIGIN` (the Vercel address, no slash at the end).

**Vercel (frontend):** `VITE_API_URL` (the Render address, no slash at the end).

## Things to know

- The Render free service sleeps after 15 minutes without visitors. The first request
  after that takes about a minute.
- PDF reports and the daily AI-call counter are files on the Render disk. They are lost
  when the service restarts. Datasets, history and accounts live in Neon and are kept.
- If you change the Vercel address, update `FRONTEND_ORIGIN` on Render and redeploy.
