import sqlite3

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"), "SECRET_KEY": "test"})
    return app.test_client()


def test_catalog_has_exact_counts(client):
    response = client.get("/api/questions?section=python")
    assert response.status_code == 200
    assert len(response.json) == 100
    assert {item["difficulty"] for item in response.json} == {"easy", "medium", "hard"}
    with sqlite3.connect(client.application.config["DATABASE"]) as db:
        rows = db.execute("SELECT section, difficulty, COUNT(*) FROM questions GROUP BY section, difficulty").fetchall()
    assert len(rows) == 9
    counts = {(section, level): count for section, level, count in rows}
    for section in ("python", "sql", "vba"):
        assert counts[(section, "easy")] == 50
        assert counts[(section, "medium")] == 30
        assert counts[(section, "hard")] == 20


def test_filters_and_rejects_invalid_section(client):
    assert len(client.get("/api/questions?section=sql&difficulty=hard").json) == 20
    assert client.get("/api/questions?section=ruby").status_code == 400


def test_answer_validation_tracks_progress(client):
    question = client.get("/api/questions?section=python").json[0]
    wrong = client.post(f"/api/answer/{question['id']}", json={"answer": "nope"})
    assert wrong.status_code == 200 and wrong.json["correct"] is False
    correct = client.post(f"/api/answer/{question['id']}", json={"answer": "[n ** 2 for n in range(11) if n % 2 == 0]"})
    assert correct.json["correct"] is True
    progress = client.get("/api/progress").json
    python = next(row for row in progress if row["section"] == "python")
    assert python["attempts"] == 2 and python["correct"] == 1


def test_answer_input_is_bounded(client):
    question = client.get("/api/questions?section=vba").json[0]
    assert client.post(f"/api/answer/{question['id']}", json={"answer": "x" * 10001}).status_code == 400


def test_python_exercise_metadata_and_runner(client):
    question = client.get("/api/questions?section=python").json[0]
    assert question["starter_code"].startswith("def even_squares")
    assert len(question["examples"]) == 2
    passed = client.post(f"/api/run/{question['id']}", json={"code": question["starter_code"].replace("    pass", "    return [number ** 2 for number in nums if number % 2 == 0]")})
    assert passed.status_code == 200 and passed.json["status"] == "passed"
    syntax = client.post(f"/api/run/{question['id']}", json={"code": "def even_squares(nums)\n    pass"})
    assert syntax.json["status"] == "syntax_error"
