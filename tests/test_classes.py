from datetime import datetime, timezone

import pytest

from grove import db, schedule
from grove.pipelines import classes
from grove.web import create_app


def raw(crn, subject, number, days, begin, end, building="Weir Hall", room="106", seq="01",
        title="Intro to Computing"):
    mt = {d: d in days for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
    mt.update({"beginTime": begin, "endTime": end, "buildingDescription": building, "room": room,
               "startDate": "08/24/2026", "endDate": "12/11/2026"})
    return {"courseReferenceNumber": crn, "subject": subject, "courseNumber": number, "sequenceNumber": seq,
            "courseTitle": title.replace("&", "&amp;"),
            "faculty": [{"displayName": "Smith, Jane", "primaryIndicator": True}],
            "meetingsFaculty": [{"meetingTime": mt}]}


SECTIONS = [
    classes.parse_section(raw("10001", "CSCI", "211", ["monday", "wednesday", "friday"], "1300", "1350")),
    classes.parse_section(raw("10002", "MATH", "261", ["tuesday", "thursday"], "0930", "1045",
                              building="Hume Hall", room="201", title="Calculus & Analytic Geometry")),
    classes.parse_section(raw("10003", "WRIT", "250", [], None, None, building="", room="")),
]


def test_parse_section():
    s = SECTIONS[1]
    assert (s["crn"], s["label"], s["title"], s["instructor"]) == (
        "10002", "MATH 261", "Calculus & Analytic Geometry", "Smith, Jane")
    assert s["meetings"] == [{"days": "TR", "begin": "09:30", "end": "10:45", "where": "Hume Hall 201",
                              "start_date": "2026-08-24", "end_date": "2026-12-11"}]
    assert SECTIONS[2]["meetings"][0]["begin"] is None and SECTIONS[2]["meetings"][0]["where"] is None


class FakeClient:
    def get_subjects(self, term):
        return [{"code": "CSCI"}, {"code": "MATH"}, {"code": "BROKEN"}]

    def search_subject(self, term, subject):
        if subject == "BROKEN":
            raise ConnectionError("timeout")
        return [raw("10001", "CSCI", "211", ["monday"], "1300", "1350")] if subject == "CSCI" else \
               [raw("10002", "MATH", "261", ["tuesday"], "0930", "1045")]


def test_fetch_stores_sections_and_replaces_the_term(conn, monkeypatch):
    monkeypatch.setenv("GROVE_TERM", "202710")
    db.replace_sections(conn, "202710", [{"crn": "99999", "label": "OLD 100", "meetings": []}])
    result = classes.fetch(conn, FakeClient())
    assert result == {"term": "202710", "count": 2, "failed_subjects": 1}
    assert {s["crn"] for s in db.get_sections(conn, "202710", ["10001", "10002", "99999"])} == {"10001", "10002"}


def test_fetch_needs_term(conn, monkeypatch):
    monkeypatch.delenv("GROVE_TERM", raising=False)
    with pytest.raises(RuntimeError, match="GROVE_TERM"):
        classes.fetch(conn, FakeClient())


def test_clean_crns():
    assert schedule.clean_crns("10001, 10002 10001,abc;1234567,") == ["10001", "10002"]
    assert len(schedule.clean_crns(" ".join(str(10000 + i) for i in range(30)))) == schedule.MAX_CRNS


@pytest.fixture
def loaded(conn, monkeypatch):
    monkeypatch.setenv("GROVE_TERM", "202710")
    db.replace_sections(conn, "202710", SECTIONS)
    return conn


def test_next_class_today(loaded):
    # Wednesday Oct 7, 10 a.m. in Oxford (CDT = UTC-5)
    d = schedule.my_classes(loaded, ["10001", "10002", "10003", "55555"],
                            now=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))
    assert d["next"]["label"] == "CSCI 211" and d["next"]["time"] == "1:00 PM" and d["next"]["day"] == "Today"
    assert d["next"]["where"] == "Weir Hall 106" and d["next"]["in_progress"] is False
    assert [o["label"] for o in d["today"]] == ["CSCI 211"]
    assert d["missing"] == ["55555"]
    assert [c["label"] for c in d["classes"]] == ["CSCI 211-01", "MATH 261-01", "WRIT 250-01"]
    assert d["classes"][1]["meetings"] == ["TR 9:30 AM–10:45 AM · Hume Hall 201"]
    assert d["classes"][2]["meetings"] == ["Time TBA"]


def test_class_in_progress_then_tomorrow(loaded):
    during = schedule.my_classes(loaded, ["10001", "10002"], now=datetime(2026, 10, 7, 18, 20, tzinfo=timezone.utc))
    assert during["next"]["label"] == "CSCI 211" and during["next"]["in_progress"] is True
    after = schedule.my_classes(loaded, ["10001", "10002"], now=datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc))
    assert after["today"] == [] and after["next"]["label"] == "MATH 261" and after["next"]["day"] == "Tomorrow"


def test_no_classes_after_the_term(loaded):
    d = schedule.my_classes(loaded, ["10001"], now=datetime(2026, 12, 20, 15, 0, tzinfo=timezone.utc))
    assert d["next"] is None and d["today"] == []


def test_not_set_up(conn, monkeypatch):
    monkeypatch.delenv("GROVE_TERM", raising=False)
    assert schedule.my_classes(conn, ["10001"]) == {"set_up": False}


def test_api(database, monkeypatch):
    monkeypatch.setenv("GROVE_TERM", "202710")
    conn = db.connect(database)
    db.replace_sections(conn, "202710", SECTIONS)
    conn.close()
    client = create_app(database).test_client()
    r = client.get("/api/classes?crns=10001,10002")
    assert r.headers["Cache-Control"] == "private, no-store"
    assert [c["crn"] for c in r.get_json()["classes"]] == ["10001", "10002"]
    assert client.get("/api/classes?crns=' OR 1=1 --").get_json()["classes"] == []
