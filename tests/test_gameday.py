import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from grove import db, widgets
from grove.pipelines import gameday

ICS = (Path(__file__).parent / "fixtures" / "football.ics").read_text()


def test_parse_calendar():
    games = gameday.parse(ICS, "football")
    assert [(g["opponent"], g["home"]) for g in games] == [
        ("LSU", True), ("Georgia", False), ("Mississippi State (Egg Bowl)", True), ("Texas", None)]
    lsu, uga, egg, texas = games
    assert lsu["start"] == "2026-10-10T23:30+00:00" and lsu["all_day"] is False
    assert lsu["location"] == "Oxford, Miss." and lsu["tv"] == "SEC Network"
    assert lsu["url"] == "https://example.com/schedule/lsu"
    assert uga["start"] == "2026-10-17T16:00+00:00"   # noon Eastern
    assert egg["start"] == "2026-11-28" and egg["all_day"] is True   # time TBA
    assert texas["start"] == "2026-10-24T22:00+00:00"  # no timezone given: campus time


def test_matchup_doubleheader_and_no_vs():
    assert gameday.matchup("Baseball vs. Arkansas (DH)", "") == ("Arkansas", True)
    assert gameday.matchup("Baseball @ Alabama", "") == ("Alabama", False)
    assert gameday.matchup("Fan Day", "") == ("Fan Day", None)


def test_calendars_env(monkeypatch):
    monkeypatch.setenv("GAMEDAY_CALENDARS", "football=https://a/f.ics junk baseball=ftp://b soccer=http://c/s.ics")
    assert gameday.calendars() == [("football", "https://a/f.ics"), ("soccer", "http://c/s.ics")]


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_keeps_window_and_sorts(monkeypatch):
    monkeypatch.setenv("GAMEDAY_CALENDARS", "football=https://a/f.ics baseball=https://b/broken")
    monkeypatch.setattr(gameday.requests, "get", lambda url, **kw:
                        FakeResponse(ICS) if url == "https://a/f.ics" else FakeResponse(status=500))
    games = gameday.fetch(now=datetime(2026, 10, 15, tzinfo=timezone.utc))["games"]
    # LSU (Oct 10) is more than 2 days old, so it's dropped.
    assert [g["opponent"] for g in games] == ["Georgia", "Texas", "Mississippi State (Egg Bowl)"]


ESPN = json.loads((Path(__file__).parent / "fixtures" / "espn_schedule.json").read_text())


def test_parse_espn_schedule():
    lsu, uga, texas = gameday.parse_espn(ESPN, "football")
    assert lsu == {"sport": "football", "opponent": "LSU", "home": True, "start": "2026-10-10T23:30+00:00",
                   "all_day": False, "location": "Vaught-Hemingway Stadium, Oxford", "tv": "SECN", "url": None}
    # Time not announced yet: kept as a date only, in Oxford's calendar (05:00 UTC is still Oct 17 there).
    assert (uga["opponent"], uga["home"], uga["start"], uga["all_day"]) == ("Georgia", False, "2026-10-17", True)
    assert (texas["home"], texas["tv"]) == (None, "ESPN")  # neutral site


def test_espn_seasons():
    from datetime import date
    assert gameday.espn_season("football", date(2026, 10, 7)) == 2026
    assert gameday.espn_season("football", date(2027, 1, 2)) == 2026      # bowl season
    assert gameday.espn_season("basketball", date(2026, 11, 10)) == 2027  # 2026-27 season
    assert gameday.espn_season("baseball", date(2027, 3, 1)) == 2027


def test_fetch_uses_espn_without_calendar_links(monkeypatch):
    monkeypatch.delenv("GAMEDAY_CALENDARS", raising=False)
    calls = []

    def fake_get(url, **kw):
        calls.append((url.split("/sports/")[1], kw["params"]))
        if "football" in url:
            return FakeJSON(ESPN)
        if "baseball" in url:
            return FakeResponse(status=500)
        return FakeJSON({"events": []})
    monkeypatch.setattr(gameday.requests, "get", fake_get)
    games = gameday.fetch(now=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))["games"]
    assert [g["opponent"] for g in games] == ["LSU", "Georgia", "Texas"]
    assert calls[0] == ("football/college-football/teams/145/schedule", {"season": 2026})
    assert ("basketball/mens-college-basketball/teams/145/schedule", {"season": 2027}) in calls


def test_fetch_with_nothing_anywhere_raises(monkeypatch):
    monkeypatch.delenv("GAMEDAY_CALENDARS", raising=False)
    monkeypatch.setattr(gameday.requests, "get", lambda url, **kw: FakeResponse(status=500))
    with pytest.raises(RuntimeError, match="no games found"):
        gameday.fetch()


class FakeJSON(FakeResponse):
    def __init__(self, data):
        super().__init__()
        self.data = data

    def json(self):
        return self.data


def save_games(conn):
    db.save_data(conn, "gameday", {"games": gameday.parse(ICS, "football")})


def test_widget_game_day(conn):
    save_games(conn)
    # 3 p.m. in Oxford on Oct 10, kickoff at 6:30 p.m.
    w = widgets.gameday(conn, now=datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc))
    d = w["data"]
    assert d["today"]["opponent"] == "LSU" and d["upcoming"][0]["live"] is False
    assert d["this_week"] is None  # Georgia is a week out


def test_widget_game_week(conn):
    save_games(conn)
    d = widgets.gameday(conn, now=datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc))["data"]  # Monday
    assert d["today"] is None and d["this_week"]["opponent"] == "Georgia"


def test_widget_live_then_over(conn):
    save_games(conn)
    live = widgets.gameday(conn, now=datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc))["data"]
    assert live["upcoming"][0]["opponent"] == "LSU" and live["upcoming"][0]["live"] is True
    after = widgets.gameday(conn, now=datetime(2026, 10, 11, 5, 0, tzinfo=timezone.utc))["data"]
    assert after["upcoming"][0]["opponent"] == "Georgia"
    # 11 p.m. Oct 10 in Oxford is still Oct 10 there: the LSU game is over, so no game-day banner.
    assert after["today"] is None


def test_widget_tba_game_counts_all_day(conn):
    save_games(conn)
    d = widgets.gameday(conn, now=datetime(2026, 11, 28, 22, 0, tzinfo=timezone.utc))["data"]
    assert d["today"]["opponent"] == "Mississippi State (Egg Bowl)"
    assert d["upcoming"][0]["live"] is False


def test_widget_not_set_up(conn):
    w = widgets.gameday(conn)
    assert w["data"] is None and w["empty"] is True


def test_kickoff_forecast_and_game_day_info(conn, tmp_path):
    save_games(conn)
    # LSU kicks off 6:30 p.m. Oxford time on Oct 10, which is in the 6 p.m. forecast hour.
    db.save_data(conn, "weather", {"forecast": [
        {"t": "2026-10-10T17:00", "temp": 75, "code": 0, "day": 1, "rain": 0},
        {"t": "2026-10-10T18:00", "temp": 72, "code": 2, "day": 1, "rain": 20},
    ]})
    (tmp_path / "gameday_info.json").write_text(
        '{"tips": [{"title": "Parking & shuttles", "url": "https://example.com/parking"},'
        ' {"title": "Bad link", "url": "javascript:alert(1)"}, {"nope": true}],'
        ' "notes": {"2026-10-10": "Homecoming game: arrive early."}}')
    d = widgets.gameday(conn, now=datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc), directory=tmp_path)["data"]
    assert d["upcoming"][0]["forecast"] == {"temp": 72, "text": "Partly cloudy", "icon": "cloud-sun", "rain": 20}
    assert d["tips"] == [{"title": "Parking & shuttles", "text": None, "url": "https://example.com/parking"},
                         {"title": "Bad link", "text": None, "url": None}]
    assert d["notes"] == "Homecoming game: arrive early."


def test_no_forecast_for_away_games_or_beyond_forecast(conn):
    save_games(conn)
    db.save_data(conn, "weather", {"forecast": []})
    after_lsu = widgets.gameday(conn, now=datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc))["data"]
    assert after_lsu["upcoming"][0]["opponent"] == "Georgia" and after_lsu["upcoming"][0]["forecast"] is None
