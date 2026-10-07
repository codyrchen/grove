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
    assert g == {"id": "402", "start": "2026-10-10T23:30Z", "state": "in", "detail": "3rd 4:12",
                 "home": True, "us": 24, "them": 17, "opponent": "LSU", "opponent_abbr": "LSU",
                 "won": None, "tv": "SEC Network"}


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


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.fixture
def scheduled(conn):
    db.save_data(conn, "gameday", {"games": [
        {"sport": "football", "opponent": "LSU", "home": True, "start": KICKOFF, "all_day": False},
        {"sport": "baseball", "opponent": "X", "home": True, "start": "2026-10-11T18:00+00:00", "all_day": False},
    ]})
    return conn


def test_no_requests_outside_game_window(scheduled, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("should not call ESPN")
    monkeypatch.setattr(scores.requests, "get", boom)
    assert scores.fetch(scheduled, now=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)) is None
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)) is None
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)) is None  # baseball


def test_fetch_during_game_then_stops_once_final(scheduled, monkeypatch):
    calls = []
    monkeypatch.setattr(scores.requests, "get", lambda url, **kw: calls.append(kw["params"]) or FakeResponse(RAW))
    data = scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))
    assert data["game"]["us"] == 24
    assert calls == [{"dates": "20261010", "groups": "80", "limit": "300"}]  # Oxford's date, not UTC's

    final = dict(data["game"], state="post", won=True)
    db.save_data(scheduled, "scores", {"game": final})
    assert scores.fetch(scheduled, now=datetime(2026, 10, 11, 2, 0, tzinfo=timezone.utc)) is None
    assert len(calls) == 1


def test_fetch_errors_when_game_missing(scheduled, monkeypatch):
    monkeypatch.setattr(scores.requests, "get", lambda url, **kw: FakeResponse({"events": []}))
    with pytest.raises(RuntimeError, match="not found"):
        scores.fetch(scheduled, now=datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc))


def test_score_on_game_day_card_then_expires(scheduled):
    db.save_data(scheduled, "scores", {"game": scores.parse(RAW)})
    live = widgets.gameday(scheduled, now=datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc))["data"]
    assert live["score"]["detail"] == "3rd 4:12"
    later = widgets.gameday(scheduled, now=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc))["data"]
    assert later["score"] is None  # more than 36 hours after kickoff
