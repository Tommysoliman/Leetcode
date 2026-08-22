# Code Atlas

A Flask + SQLite practice app for Python, SQL, and VBA. Each track contains 100 curated questions: 50 easy, 30 medium, and 20 hard.

## Install

Use Python 3.11 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run locally

```powershell
python app.py
```

Open http://127.0.0.1:5000. The database is created as `quiz.sqlite3` on first start. Set `QUIZ_DATABASE` to use another SQLite path and set a strong `SECRET_KEY` outside development.

## Test

```powershell
python -m pytest -q
```

## Question data

All question records live in [quiz_data.py](quiz_data.py). The `PYTHON_CONCEPTS`, `SQL_CONCEPTS`, and `VBA_CONCEPTS` catalogs are transformed into database rows at startup. Import-time assertions enforce 300 total records and the 50/30/20 difficulty split for every section.

## Deploy

### GitHub

Create an empty repository on GitHub, then run these commands from this folder:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git branch -M main
git push -u origin main
```

Do not commit `.env`; it is excluded by `.gitignore`.

### Railway

1. Sign in at https://railway.app and choose **New Project**.
2. Select **Deploy from GitHub repo** and choose this repository.
3. Railway will use `railway.toml` and start the app with Gunicorn.
4. In the Railway service's **Variables** panel, add `SECRET_KEY`, `OPEN_API_KEY`, and optionally `OPENAI_MODEL`.
5. Add a persistent volume and set `QUIZ_DATABASE` to a path on that volume, such as `/data/quiz.sqlite3`.
6. Generate a public domain from the service's **Networking** panel.

The OpenAI key belongs only in Railway variables or the local `.env`; the browser never receives it. Railway does not upload your local `.env`, so add `OPENAI_API_KEY` manually under the service's **Variables** tab and trigger a redeploy. The app also accepts the legacy name `OPEN_API_KEY`.

For a small production deployment, install dependencies in the server environment and run a production WSGI server:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-value"
$env:QUIZ_DATABASE = "C:\data\code-atlas.sqlite3"
python -m gunicorn --bind 0.0.0.0:8000 app:app
```

On Linux, use `gunicorn --bind 0.0.0.0:8000 app:app` and place a reverse proxy such as nginx or a managed platform in front of it. Use persistent storage for SQLite, HTTPS at the proxy, environment-managed secrets, and regular database backups. For multiple application instances or high write concurrency, move the database layer to PostgreSQL.
