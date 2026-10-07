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


def test_fetch_not_configured(monkeypatch):
    monkeypatch.delenv("GAMEDAY_CALENDARS", raising=False)
    with pytest.raises(RuntimeError, match="GAMEDAY_CALENDARS"):
        gameday.fetch()


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
    assert w["data"] is None and "isn't set up" in w["message"]
