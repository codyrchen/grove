import json
from datetime import datetime, timezone

from grove import widgets

PLACES = [
    {"name": "Late Spot", "hours": {d: ["18:00-02:00"] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}},
    {"name": "Lunch Place", "menu_url": "https://example.com/menu",
     "hours": {"mon": ["07:00-10:00", "11:00-14:00"], "tue": ["07:00-10:00", "11:00-14:00"],
               "wed": ["07:00-10:00", "11:00-14:00"], "thu": ["07:00-14:00"], "fri": ["07:00-14:00"]},
     "closed": ["2026-10-08"]},
    {"name": "Weekend Cafe", "hours": {"sat": ["09:00-12:00"]}, "special": {"2026-10-07": ["12:00-13:30"]}},
]


def at(month, day, hour, minute=0):
    """A time in Oxford (CDT, UTC-5) as UTC."""
    return datetime(2026, month, day, hour + 5, minute, tzinfo=timezone.utc) if hour + 5 < 24 else \
        datetime(2026, month, day + 1, hour + 5 - 24, minute, tzinfo=timezone.utc)


def run(tmp_path, now):
    (tmp_path / "dining.json").write_text(json.dumps(PLACES))
    return {p["name"]: p for p in widgets.dining(now, tmp_path)["data"]["places"]}


def test_open_now_and_closing_soon(tmp_path):
    p = run(tmp_path, at(10, 7, 13, 40))  # Wednesday 1:40 p.m.
    assert p["Lunch Place"]["open"] and p["Lunch Place"]["text"] == "Closes in 20 min"
    assert p["Lunch Place"]["closing_soon"] is True
    assert p["Weekend Cafe"]["text"] == "Opens Saturday 9 AM"  # special hours today already ended
    assert p["Late Spot"]["text"] == "Opens 6 PM"


def test_between_meals(tmp_path):
    p = run(tmp_path, at(10, 7, 10, 30))  # Wednesday 10:30 a.m.
    assert p["Lunch Place"]["text"] == "Opens 11 AM"
    assert p["Weekend Cafe"]["text"] == "Opens 12 PM"


def test_past_midnight_and_holiday(tmp_path):
    p = run(tmp_path, at(10, 8, 1, 15))  # Thursday 1:15 a.m.: still Wednesday night's hours
    assert p["Late Spot"]["open"] and p["Late Spot"]["text"] == "Closes in 45 min"
    assert p["Lunch Place"]["text"] == "Opens tomorrow 7 AM"  # Thursday is a closed day; Friday is tomorrow


def test_order_and_counts(tmp_path):
    (tmp_path / "dining.json").write_text(json.dumps(PLACES))
    d = widgets.dining(at(10, 7, 21, 0), tmp_path)["data"]  # 9 p.m.
    assert [p["name"] for p in d["places"]][0] == "Late Spot"
    assert d["open_count"] == 1 and d["late_night"] is True
    assert d["places"][1]["menu_url"] == "https://example.com/menu"


def test_bad_hours_are_skipped(tmp_path):
    (tmp_path / "dining.json").write_text(json.dumps([{"name": "Typo", "hours": {"wed": ["7am-9pm", 5]}}]))
    [p] = widgets.dining(at(10, 7, 12), tmp_path)["data"]["places"]
    assert p["text"] == "Closed" and not p["open"]


def test_empty(tmp_path):
    assert widgets.dining(at(10, 7, 12), tmp_path) == {"data": None, "empty": True}
