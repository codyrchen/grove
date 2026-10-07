from datetime import datetime, timezone
from pathlib import Path

from grove import db, ics, widgets
from grove.pipelines import events

ICS = (Path(__file__).parent / "fixtures" / "events.ics").read_text()
# 3 p.m. in Oxford on Oct 7
AFTERNOON = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)


def test_parse_and_food_tags():
    found = events.parse(ICS, "campus")
    by_title = {e["title"]: e for e in found}
    assert by_title["Study Break with Free Pizza"]["food"] is True
    assert by_title["Club Meeting"]["food"] is True          # food mentioned in the description
    assert by_title["Live Music on the Square"]["food"] is False
    assert by_title["Live Music on the Square"]["location"] == "The Square, Oxford"
    assert by_title["Career Fair"]["all_day"] is True


def test_food_words_are_whole_words():
    assert events.has_food("Taco Tuesday")
    assert not events.has_food("Snackbar Theory Lecture")  # "snack" inside another word
    assert not events.has_food("Pizzazz Dance Recital")


def test_feeds_parser():
    assert ics.feeds("campus=https://a/e.ics oops oxford=http://b/c.ics x=ftp://y") == [
        ("campus", "https://a/e.ics"), ("oxford", "http://b/c.ics")]


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_dedupes_across_feeds_and_drops_far_future(monkeypatch):
    monkeypatch.setenv("EVENTS_CALENDARS", "campus=https://a/e.ics oxford=https://b/e.ics")
    monkeypatch.setattr(events.requests, "get", lambda url, **kw: FakeResponse(ICS))
    found = events.fetch(now=AFTERNOON)["events"]
    titles = [e["title"] for e in found]
    assert len(titles) == len(set(titles)) == 5
    assert "Far Future Event" not in titles


def test_tonight_widget(conn):
    db.save_data(conn, "events", {"events": events.parse(ICS, "campus")})
    w = widgets.tonight(conn, now=AFTERNOON)
    d = w["data"]
    # Morning Yoga is over; tonight's events come first, the all-day fair last.
    assert [e["title"] for e in d["today"]] == [
        "Study Break with Free Pizza", "Live Music on the Square", "Career Fair"]
    assert d["today"][0]["evening"] is True and d["today"][0]["happening"] is False
    assert [e["title"] for e in d["soon"]] == ["Club Meeting"]
    assert d["food_count"] == 2 and w["empty"] is False


def test_tonight_happening_now(conn):
    db.save_data(conn, "events", {"events": events.parse(ICS, "campus")})
    d = widgets.tonight(conn, now=datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc))["data"]
    assert d["today"][0]["title"] == "Study Break with Free Pizza" and d["today"][0]["happening"]


def test_tonight_hidden_until_set_up(conn):
    assert widgets.tonight(conn)["empty"] is True
