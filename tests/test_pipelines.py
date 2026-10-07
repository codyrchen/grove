import json
from pathlib import Path

import pytest

from grove.pipelines import news, weather

FIXTURES = Path(__file__).parent / "fixtures"


def test_weather_parse():
    w = weather.parse(json.loads((FIXTURES / "open_meteo.json").read_text()))
    assert (w["temp"], w["feels_like"], w["wind_mph"]) == (61, 60, 6)
    assert (w["text"], w["icon"]) == ("Partly cloudy", "cloud-sun")
    assert w["sunset"] == "6:31 PM"
    assert weather.clock("2026-10-08T00:05") == "12:05 AM"
    assert len(w["days"]) == 5
    assert w["days"][2] == {"date": "2026-10-09", "high": 70, "low": 59, "rain_chance": 85,
                            "text": "Thunderstorms", "icon": "cloud-lightning-rain", "code": 95}
    assert w["code"] == 2


def test_weather_upcoming_hours():
    w = weather.parse(json.loads((FIXTURES / "open_meteo.json").read_text()))
    # Current time in the fixture is 08:00, so the row starts at 9 am, every 3 hours.
    assert [(h["label"], h["temp"]) for h in w["hours"]] == [
        ("9 am", 58), ("12 pm", 68), ("3 pm", 72), ("6 pm", 68), ("9 pm", 58)]
    assert w["hours"][4]["icon"] == "cloud-moon"  # partly cloudy at night


def test_weather_keeps_full_hourly_forecast():
    w = weather.parse(json.loads((FIXTURES / "open_meteo.json").read_text()))
    assert len(w["forecast"]) == 48
    assert w["forecast"][18] == {"t": "2026-10-07T18:00", "temp": 68, "code": 2, "day": 1, "rain": None}


def test_weather_without_hourly_data():
    raw = json.loads((FIXTURES / "open_meteo.json").read_text())
    del raw["hourly"]
    assert weather.parse(raw)["hours"] == []


def test_weather_night_icon_and_unknown_code():
    assert weather.describe(0, is_day=False) == ("Clear", "moon-stars")
    assert weather.describe(2, is_day=False) == ("Partly cloudy", "cloud-moon")
    assert weather.describe(1234) == ("—", "cloud")


def test_rss_parse():
    items = news.parse((FIXTURES / "news_rss.xml").read_bytes())
    assert [i["title"] for i in items] == [
        "Students Explore Research at Fall Symposium – Day One",
        "Library Extends Hours for Midterms",
    ]  # the javascript: link is dropped
    first, second = items
    assert first["url"] == "https://news.olemiss.edu/students-explore-research/"
    assert first["date"] == "2026-10-06T14:00:00+00:00"
    assert first["summary"] == "More than 200 students presented work."
    assert first["image"] == "https://news.olemiss.edu/wp-content/uploads/symposium.jpg"
    assert second["date"] == "2026-10-05T14:30:00+00:00"
    assert second["image"] == "https://news.olemiss.edu/wp-content/uploads/library.jpg"


def test_atom_parse():
    [item] = news.parse((FIXTURES / "news_atom.xml").read_bytes())
    assert item["url"] == "https://example.olemiss.edu/rebels-win"
    assert item["date"] == "2026-10-04T22:15:00+00:00"
    assert item["summary"] == "A big win in Vaught-Hemingway Stadium."


class FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_news_fetch_merges_feeds_and_survives_a_bad_one(monkeypatch):
    monkeypatch.setenv("NEWS_FEEDS", "https://a/rss https://b/broken https://c/atom")
    pages = {"https://a/rss": FakeResponse((FIXTURES / "news_rss.xml").read_bytes()),
             "https://b/broken": FakeResponse(status=500),
             "https://c/atom": FakeResponse((FIXTURES / "news_atom.xml").read_bytes())}
    monkeypatch.setattr(news.requests, "get", lambda url, **kw: pages[url])
    items = news.fetch()["items"]
    assert [i["title"] for i in items][:1] == ["Students Explore Research at Fall Symposium – Day One"]
    assert len(items) == 3  # newest first, all feeds merged


def test_news_fetch_with_nothing_raises(monkeypatch):
    monkeypatch.setenv("NEWS_FEEDS", "https://b/broken")
    monkeypatch.setattr(news.requests, "get", lambda url, **kw: FakeResponse(status=500))
    with pytest.raises(RuntimeError, match="no news items"):
        news.fetch()
