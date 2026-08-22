import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from dotenv import load_dotenv

from quiz_data import QUESTIONS

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
QUESTION_METADATA = {(item["section"], item["number"]): item for item in QUESTIONS}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("QUIZ_DATABASE", str(BASE_DIR / "quiz.sqlite3")),
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
    )
    if test_config:
        app.config.update(test_config)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    def init_db():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY,
                section TEXT NOT NULL CHECK (section IN ('python', 'sql', 'vba')),
                number INTEGER NOT NULL,
                difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                UNIQUE(section, number)
            );
            CREATE TABLE IF NOT EXISTS progress (
                question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
                attempts INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                last_answer TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        existing = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if existing == 0:
            db.executemany("""INSERT INTO questions
                (section, number, difficulty, title, prompt, answer, explanation)
                VALUES (:section, :number, :difficulty, :title, :prompt, :answer, :explanation)""", QUESTIONS)
            db.commit()

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Database initialized.")

    with app.app_context():
        init_db()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/questions")
    def questions():
        section = request.args.get("section", "python")
        difficulty = request.args.get("difficulty", "all")
        if section not in {"python", "sql", "vba"}:
            return jsonify({"error": "Invalid section"}), 400
        query = "SELECT id, section, number, difficulty, title, prompt FROM questions WHERE section = ?"
        params = [section]
        if difficulty != "all":
            if difficulty not in {"easy", "medium", "hard"}:
                return jsonify({"error": "Invalid difficulty"}), 400
            query += " AND difficulty = ?"
            params.append(difficulty)
        query += " ORDER BY number"
        rows = []
        for row in get_db().execute(query, params):
            item = dict(row)
            metadata = QUESTION_METADATA[(item["section"], item["number"])]
            item.update({key: metadata[key] for key in ("prompt", "examples", "starter_code", "hints", "tags", "function_name")})
            rows.append(item)
        return jsonify(rows)

    @app.get("/api/progress")
    def progress():
        rows = get_db().execute("""
            SELECT q.section, COUNT(q.id) total, COALESCE(SUM(p.correct), 0) correct,
                   COALESCE(SUM(p.attempts), 0) attempts
            FROM questions q LEFT JOIN progress p ON p.question_id = q.id
            GROUP BY q.section ORDER BY q.section
        """).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/api/answer/<int:question_id>")
    def answer(question_id):
        payload = request.get_json(silent=True) or {}
        submitted = payload.get("answer")
        if not isinstance(submitted, str) or len(submitted) > 10000:
            return jsonify({"error": "Answer must be a text value under 10,000 characters"}), 400
        row = get_db().execute("SELECT answer, explanation FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Question not found"}), 404
        normalize = lambda value: " ".join(value.strip().casefold().split())
        expected = normalize(row["answer"])
        actual = normalize(submitted)
        correct = hmac.compare_digest(hashlib.sha256(actual.encode()).digest(), hashlib.sha256(expected.encode()).digest())
        db = get_db()
        db.execute("""INSERT INTO progress(question_id, attempts, correct, last_answer)
            VALUES (?, 1, ?, ?) ON CONFLICT(question_id) DO UPDATE SET
            attempts = attempts + 1, correct = correct + excluded.correct,
            last_answer = excluded.last_answer, updated_at = CURRENT_TIMESTAMP""",
            (question_id, int(correct), submitted))
        db.commit()
        return jsonify({"correct": correct, "expected": row["answer"] if correct else None,
                        "explanation": row["explanation"]})

    @app.get("/api/answer/<int:question_id>")
    def reveal_answer(question_id):
        row = get_db().execute("SELECT answer, explanation FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Question not found"}), 404
        return jsonify({"answer": row["answer"], "explanation": row["explanation"]})

    @app.post("/api/run/<int:question_id>")
    def run_code(question_id):
        payload = request.get_json(silent=True) or {}
        code = payload.get("code")
        row = get_db().execute("SELECT section, number FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Question not found"}), 404
        if row["section"] != "python":
            return jsonify({"error": "The code runner currently supports Python exercises."}), 400
        metadata = QUESTION_METADATA[(row["section"], row["number"])]
        if not metadata["function_name"]:
            return jsonify({"error": "This question does not yet have an executable test harness."}), 400
        if not isinstance(code, str) or len(code) > 12000:
            return jsonify({"error": "Code must be text under 12,000 characters"}), 400
        harness = textwrap.dedent(f"""
            import json
            import {metadata['function_name']}
        """)
        cases = metadata["test_cases"]
        test_script = "\n".join([
            "import json",
            code,
            "results = []",
            "cases = " + repr(cases),
            f"for index, case in enumerate(cases, 1):",
            f"    try:\n        actual = {metadata['function_name']}(*case['args'])\n        expected = case['expected']\n        results.append({{'index': index, 'passed': actual == expected, 'actual': repr(actual), 'expected': repr(expected)}})",
            "    except Exception as error:",
            "        results.append({'index': index, 'passed': False, 'error': f'{type(error).__name__}: {error}'})",
            "print(json.dumps(results))",
        ])
        try:
            completed = subprocess.run([sys.executable, "-I", "-c", test_script], capture_output=True, text=True, timeout=3, cwd=tempfile.gettempdir())
        except subprocess.TimeoutExpired:
            return jsonify({"status": "timeout", "message": "Your code took too long. Look for an infinite loop."})
        if completed.returncode != 0:
            return jsonify({"status": "syntax_error" if "SyntaxError" in completed.stderr else "runtime_error", "message": completed.stderr[-2000:]})
        try:
            results = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return jsonify({"status": "runtime_error", "message": "The runner could not read your result."}), 500
        return jsonify({"status": "passed" if all(item["passed"] for item in results) else "failed", "tests": results, "passed_count": sum(item["passed"] for item in results), "test_count": len(results)})

    @app.post("/api/ask-ai")
    def ask_ai():
        payload = request.get_json(silent=True) or {}
        prompt = payload.get("question")
        context = payload.get("context", "")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            return jsonify({"error": "Ask a question between 1 and 4,000 characters"}), 400
        if not isinstance(context, str) or len(context) > 12000:
            return jsonify({"error": "Question context is too large"}), 400
        api_key = os.environ.get("OPEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "AI is not configured. Add OPENAI_API_KEY (or OPEN_API_KEY) in Railway Variables, then redeploy."}), 503
        body = json.dumps({
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "input": f"You are a patient coding tutor. Explain clearly and concisely.\n\nQuiz context:\n{context}\n\nUser question:\n{prompt}",
            "max_output_tokens": 700,
        }).encode("utf-8")
        http_request = urllib.request.Request(
            "https://api.openai.com/v1/responses", data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return jsonify({"error": "The AI service could not be reached right now."}), 502
        text = result.get("output_text")
        if not text:
            text = "".join(item.get("text", "") for output in result.get("output", []) for item in output.get("content", []) if item.get("type") == "output_text")
        return jsonify({"answer": text or "The AI returned no answer."})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
