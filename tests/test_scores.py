import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from grove import db, widgets
from grove.pipelines import scores

RAW = json.loads((Path(__file__).parent / "fixtures" / "espn_scoreboard.json").read_text())
KICKOFF = "2026-10-10T23:30+00:00"


def test_parse_live_game():
    g = scores.parse(RAW)
    assert g == {"sport": "football", "id": "402", "start": "2026-10-10T23:30Z", "state": "in",
                 "detail": "3rd 4:12", "home": True, "us": 24, "them": 17, "opponent": "LSU",
                 "opponent_abbr": "LSU", "won": None, "tv": "SEC Network"}


def test_parse_final_and_wrapped_scores():
    raw = json.loads(json.dumps(RAW))
    comp = raw["events"][1]["competitions"][0]
    comp["status"]["type"] = {"state": "post", "completed": True, "shortDetail": "Final"}
    comp["competitors"][0]["score"] = {"value": 24.0, "displayValue": "24"}
    comp["competitors"][1]["score"] = {"value": 31.0, "displayValue": "31"}
    g = scores.parse(raw)
    assert (g["state"], g["us"], g["them"], g["won"]) == ("post", 24, 31, False)


def test_parse_matches_by_name_if_id_changes(monkeypatch):
    monkeypatch.setenv("SCORES_TEAM_ID", "000")
    assert scores.parse(RAW)["opponent"] == "LSU"


def test_parse_not_playing():
    assert scores.parse({"events": [RAW["events"][0]]}) is None
    assert scores.parse({}) is None


def test_parse_doubleheader_picks_closest_game():
    raw = json.loads(json.dumps(RAW))
    second = json.loads(json.dumps(raw["events"][1]))
    second["id"], second["date"] = "403", "2026-10-11T03:00Z"
    raw["events"].append(second)
    near = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)
    assert scores.parse(raw, "baseball", near=near)["id"] == "403"
    assert scores.parse(raw, "baseball", near=datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc))["id"] == "402"


def test_reads_old_single_game_format():
    assert scores.stored_games({"game": {"start": "x", "state": "post"}}) == {"football": {"start": "x", "state": "post"}}
    assert scores.stored_games(None) == {}


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.data


@pytest.fixture
def scheduled(conn):
    db.save_data(conn, "gameday", {"games": [
        {"sport": "football", "opponent": "LSU", "home": True, "start": KICKOFF, "all_day": False},
        {"sport": "basketball", "opponent": "LSU", "home": True, "start": "2026-10-11T00:00+00:00", "all_day": False},
        {"sport": "volleyball", "opponent": "X", "home": True, "start": "2026-10-11T18:00+00:00", "all_day": False},
    ]})
    return conn


def test_no_requests_outside_game_windows(scheduled, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("should not call ESPN")
    monkeypatch.setattr(scores.requests, "get", boom)
    assert scores.fetch(scheduled, now=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)) is None
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)) is None
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)) is None  # volleyball: no ESPN feed


def test_fetch_checks_each_sport_on_its_own_feed(scheduled, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append((url.split("/sports/")[1], kw["params"]))
        if "basketball" in url:
            hoops = json.loads(json.dumps(RAW))
            hoops["events"][1]["competitions"][0]["status"]["type"]["shortDetail"] = "2nd 10:21"
            return FakeResponse(hoops)
        return FakeResponse(RAW)
    monkeypatch.setattr(scores.requests, "get", fake_get)
    data = scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))
    assert data["games"]["football"]["detail"] == "3rd 4:12"
    assert data["games"]["basketball"]["detail"] == "2nd 10:21"
    assert calls == [
        ("football/college-football/scoreboard", {"dates": "20261010", "limit": "300", "groups": "80"}),
        ("basketball/mens-college-basketball/scoreboard", {"dates": "20261010", "limit": "300", "groups": "50"}),
    ]  # Oxford's date, not UTC's


def test_final_games_stop_being_checked(scheduled, monkeypatch):
    calls = []
    monkeypatch.setattr(scores.requests, "get", lambda url, **kw: calls.append(url) or FakeResponse(RAW))
    data = scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))
    for g in data["games"].values():
        g["state"] = "post"
    db.save_data(scheduled, "scores", data)
    calls.clear()
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 2, 0, tzinfo=timezone.utc)) is None
    assert calls == []


def test_one_sport_failing_keeps_the_other(scheduled, monkeypatch):
    monkeypatch.setattr(scores.requests, "get", lambda url, **kw:
                        FakeResponse({}, 500) if "basketball" in url else FakeResponse(RAW))
    data = scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))
    assert set(data["games"]) == {"football"}


def test_all_failing_raises(scheduled, monkeypatch):
    monkeypatch.setattr(scores.requests, "get", lambda url, **kw: FakeResponse({"events": []}))
    with pytest.raises(RuntimeError, match="not found"):
        scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))


def test_scores_on_game_day_card_then_expire(scheduled):
    live = dict(scores.parse(RAW), sport="basketball", start="2026-10-11T00:00Z")
    final = dict(scores.parse(RAW), state="post", won=True, start="2026-10-10T19:00Z")
    db.save_data(scheduled, "scores", {"games": {"basketball": live, "football": final}})
    d = widgets.gameday(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))["data"]
    assert [g["sport"] for g in d["scores"]] == ["basketball", "football"]  # live first
    later = widgets.gameday(scheduled, now=datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc))["data"]
    assert later["scores"] == []  # more than 36 hours later
