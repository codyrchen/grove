from datetime import datetime, timedelta, timezone

import pytest

from grove import db, widgets
from grove.web import create_app


@pytest.fixture
def client(database):
    app = create_app(database)
    app.config["TESTING"] = True
    return app.test_client()


def test_dashboard_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Oxford weather" in r.data and b"GROVE_WIDGETS" in r.data


def test_healthz_and_about(client):
    assert client.get("/healthz").data == b"ok"
    assert client.get("/about").status_code == 200


def test_widgets_before_any_data(client):
    data = client.get("/api/widgets").get_json()
    assert set(data) == {"greeting", "weather", "news", "links"}
    assert data["weather"]["data"] is None and "first time" in data["weather"]["message"]
    assert data["links"]["data"]["links"][0]["label"] == "myOleMiss"


def test_widget_with_data(client, database):
    conn = db.connect(database)
    db.save_data(conn, "weather", {"temp": 70})
    conn.close()
    w = client.get("/api/widgets/weather").get_json()
    assert w["data"] == {"temp": 70}
    assert w["updated_ago"] == "just now" and w["stale"] is False


def test_unknown_widget_404(client):
    assert client.get("/api/widgets/nope").status_code == 404


def test_stale_flag(conn):
    db.save_data(conn, "weather", {"temp": 70})
    later = datetime.now(timezone.utc) + timedelta(hours=4)
    w = widgets.stored(conn, "weather", now=later)
    assert w["stale"] is True and w["updated_ago"] == "4 hr ago"


def test_greeting(monkeypatch):
    monkeypatch.setenv("SEMESTER_START", "2026-08-24")
    monkeypatch.setenv("SEMESTER_END", "2026-12-11")
    # 13:00 UTC is 8:00 a.m. in Oxford (CDT).
    g = widgets.greeting(datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc))
    assert g["hello"] == "Good morning"
    assert g["date"] == "Wednesday, October 7"
    assert g["semester_week"] == 7
    assert g["days_left"] == 65


def test_greeting_outside_semester(monkeypatch):
    monkeypatch.setenv("SEMESTER_START", "2026-08-24")
    monkeypatch.setenv("SEMESTER_END", "2026-12-11")
    g = widgets.greeting(datetime(2026, 12, 25, 3, 0, tzinfo=timezone.utc))  # 9 p.m. Christmas Eve
    assert g["hello"] == "Good evening" and g["semester_week"] is None
