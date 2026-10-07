from datetime import datetime, timedelta, timezone

from grove import db, refresh


def test_failure_keeps_last_good_data(conn, monkeypatch):
    monkeypatch.setitem(refresh.PIPELINES, "weather", (lambda: {"temp": 70}, 1800))
    assert refresh.run(conn, "weather")

    def broken():
        raise ConnectionError("source down")
    monkeypatch.setitem(refresh.PIPELINES, "weather", (broken, 1800))
    assert not refresh.run(conn, "weather")

    row = db.load(conn, "weather")
    assert row["data"] == {"temp": 70}
    assert "source down" in row["error"]

    # A later success clears the error.
    monkeypatch.setitem(refresh.PIPELINES, "weather", (lambda: {"temp": 72}, 1800))
    refresh.run(conn, "weather")
    row = db.load(conn, "weather")
    assert row["data"] == {"temp": 72} and row["error"] is None


def test_due(conn, monkeypatch):
    monkeypatch.setitem(refresh.PIPELINES, "news", (lambda: {"items": []}, 3600))
    assert refresh.due(conn, "news")
    refresh.run(conn, "news")
    now = datetime.now(timezone.utc)
    assert not refresh.due(conn, "news", now + timedelta(minutes=30))
    assert refresh.due(conn, "news", now + timedelta(minutes=61))


def test_first_failure_with_no_data_yet(conn):
    db.save_error(conn, "news", "boom")
    row = db.load(conn, "news")
    assert row["data"] is None and row["error"] == "boom"
    assert db.last_attempt(conn, "news") == row["error_at"]


def test_nothing_to_do_keeps_data(conn, monkeypatch):
    monkeypatch.setitem(refresh.PIPELINES, "scores", (lambda: {"game": {"us": 31}}, 60))
    refresh.run(conn, "scores")
    monkeypatch.setitem(refresh.PIPELINES, "scores", (lambda: None, 60))
    assert refresh.run(conn, "scores") is True
    assert db.load(conn, "scores")["data"] == {"game": {"us": 31}}
