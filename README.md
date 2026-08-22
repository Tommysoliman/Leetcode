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

For a small production deployment, install dependencies in the server environment and run a production WSGI server:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-value"
$env:QUIZ_DATABASE = "C:\data\code-atlas.sqlite3"
python -m gunicorn --bind 0.0.0.0:8000 app:app
```

On Linux, use `gunicorn --bind 0.0.0.0:8000 app:app` and place a reverse proxy such as nginx or a managed platform in front of it. Use persistent storage for SQLite, HTTPS at the proxy, environment-managed secrets, and regular database backups. For multiple application instances or high write concurrency, move the database layer to PostgreSQL.
