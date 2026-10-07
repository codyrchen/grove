import json
from datetime import datetime, timezone

from grove import db, widgets

NOON_OCT_7 = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)


def write(tmp_path, name, data):
    (tmp_path / name).write_text(json.dumps(data))


def test_missing_or_broken_files_are_empty(tmp_path):
    (tmp_path / "trivia.json").write_text("{not json")
    assert widgets.trivia_of_the_day(NOON_OCT_7, tmp_path) is None
    assert widgets.current_moment(NOON_OCT_7, tmp_path) is None
    assert widgets.countdowns(NOON_OCT_7, tmp_path) == {"academic": []}
    assert widgets.square_feature(NOON_OCT_7, tmp_path) is None


def test_trivia_rotates_daily(tmp_path):
    write(tmp_path, "trivia.json", [{"text": "A"}, {"text": "B"}, {"text": "C"}, {"nope": 1}])
    days = {widgets.trivia_of_the_day(datetime(2026, 10, d, 17, tzinfo=timezone.utc), tmp_path)
            for d in range(1, 8)}
    assert days == {"A", "B", "C"}


def test_moment(tmp_path):
    write(tmp_path, "moments.json", [
        {"start": "2026-10-05", "end": "2026-10-10", "message": "Homecoming week!"},
        {"start": "2026-12-07", "end": "2026-12-11", "message": "Finals week", "mode": "finals"},
    ])
    assert widgets.current_moment(NOON_OCT_7, tmp_path) == {"message": "Homecoming week!", "mode": None}
    finals = widgets.current_moment(datetime(2026, 12, 9, 17, tzinfo=timezone.utc), tmp_path)
    assert finals["mode"] == "finals"
    assert widgets.current_moment(datetime(2026, 11, 1, 17, tzinfo=timezone.utc), tmp_path) is None


def test_countdowns(tmp_path):
    write(tmp_path, "academic_calendar.json", [
        {"name": "Last day to drop with a W", "date": "2026-10-30"},
        {"name": "Fall break", "date": "2026-10-12"},
        {"name": "Already passed", "date": "2026-09-01"},
        {"name": "Too far out", "date": "2027-05-01"},
        {"name": "Bad date", "date": "soon"},
    ])
    c = widgets.countdowns(NOON_OCT_7, tmp_path)["academic"]
    assert [(e["name"], e["days"]) for e in c] == [("Fall break", 5), ("Last day to drop with a W", 23)]


def test_square_feature_rotates_weekly(tmp_path):
    write(tmp_path, "square.json", [{"name": "Square Books", "url": "https://example.com", "deal": "10% off"},
                                    {"name": "Coffee Spot", "url": "javascript:alert(1)"}])
    a = widgets.square_feature(datetime(2026, 10, 5, 17, tzinfo=timezone.utc), tmp_path)  # Monday
    b = widgets.square_feature(datetime(2026, 10, 11, 17, tzinfo=timezone.utc), tmp_path)  # Sunday, same week
    c = widgets.square_feature(datetime(2026, 10, 12, 17, tzinfo=timezone.utc), tmp_path)  # next Monday
    assert a == b and a["name"] != c["name"]
    coffee = a if a["name"] == "Coffee Spot" else c
    assert coffee["url"] is None


def test_snow(conn):
    assert widgets.snowing(conn) is False
    db.save_data(conn, "weather", {"code": 3, "days": [{"code": 73}]})
    assert widgets.snowing(conn) is True
    db.save_data(conn, "weather", {"code": 61, "days": [{"code": 61}]})
    assert widgets.snowing(conn) is False


def test_shipped_data_files_are_valid():
    from grove import content
    for name in ("academic_calendar.json", "moments.json", "square.json", "trivia.json"):
        assert isinstance(content.load(name, None), list), name
    assert len(content.entries("trivia.json")) >= 5
