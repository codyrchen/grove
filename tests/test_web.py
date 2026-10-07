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
    assert b"Weather" in r.data and b"GROVE_WIDGETS" in r.data


def test_healthz_and_about(client):
    assert client.get("/healthz").data == b"ok"
    assert client.get("/about").status_code == 200


def test_widgets_before_any_data(client):
    data = client.get("/api/widgets").get_json()
    assert set(data) == {"greeting", "photo", "weather", "news", "links"}
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
    assert g["date"] == "Wednesday, October 7, 2026"
    assert g["semester_week"] == 7
    assert g["days_left"] == 65


def test_greeting_outside_semester(monkeypatch):
    monkeypatch.setenv("SEMESTER_START", "2026-08-24")
    monkeypatch.setenv("SEMESTER_END", "2026-12-11")
    g = widgets.greeting(datetime(2026, 12, 25, 3, 0, tzinfo=timezone.utc))  # 9 p.m. Christmas Eve
    assert g["hello"] == "Good evening" and g["semester_week"] is None
    assert widgets.greeting(datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc))["hello"] == "Good night"


def test_photo_of_the_day(tmp_path):
    (tmp_path / "grove.jpg").write_bytes(b"x")
    (tmp_path / "lyceum.jpg").write_bytes(b"x")
    (tmp_path / "photos.json").write_text(
        '[{"file": "grove.jpg", "place": "The Grove", "credit": "Cody"},'
        ' {"file": "lyceum.jpg", "place": "The Lyceum"},'
        ' {"file": "missing.jpg", "place": "Not on disk"},'
        ' {"file": "../secret.jpg"}]')
    day1 = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 8, 17, 0, tzinfo=timezone.utc)
    p1 = widgets.photo_of_the_day(day1, tmp_path)
    p2 = widgets.photo_of_the_day(day2, tmp_path)
    assert {p1["place"], p2["place"]} == {"The Grove", "The Lyceum"}
    assert p1["url"].startswith("/static/photos/")
    # Same photo all day in Oxford, even across the UTC date line (11 p.m. CDT is 04:00 UTC).
    assert widgets.photo_of_the_day(datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc), tmp_path) == p1


def test_no_photos_means_none(tmp_path):
    assert widgets.photo_of_the_day(directory=tmp_path) is None
