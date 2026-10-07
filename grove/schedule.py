"""A student's classes, today's meetings and their next class, from the CRNs they enter."""

import re
from datetime import date, datetime, time, timedelta, timezone

from . import db
from .config import CAMPUS_TZ
from .pipelines import classes

DAY_CODES = "MTWRFSU"  # Monday..Sunday, Banner's letters
MAX_CRNS = 12


def clean_crns(raw: str) -> list[str]:
    crns = []
    for c in re.split(r"[\s,]+", raw or ""):
        if c.isdigit() and len(c) <= 6 and c not in crns:
            crns.append(c)
    return crns[:MAX_CRNS]


def _clock(t: time) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _meets_on(m: dict, day: date) -> bool:
    if DAY_CODES[day.weekday()] not in (m.get("days") or ""):
        return False
    start, end = m.get("start_date"), m.get("end_date")
    return (not start or start <= day.isoformat()) and (not end or day.isoformat() <= end)


def _meeting_text(m: dict) -> str:
    if not m.get("begin"):
        return "Time TBA" if not m.get("days") else f'{m["days"]} · time TBA'
    begin, end = time.fromisoformat(m["begin"]), time.fromisoformat(m["end"])
    text = f'{m["days"]} {_clock(begin)}–{_clock(end)}'
    return f'{text} · {m["where"]}' if m.get("where") else text


def my_classes(conn: db.DB, crns: list[str], now: datetime | None = None) -> dict:
    term = classes.term()
    if not term:
        return {"set_up": False}
    sections = db.get_sections(conn, term, crns)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(CAMPUS_TZ).date()

    occurrences = []
    for offset in range(8):
        day = today + timedelta(days=offset)
        for s in sections:
            for m in s["meetings"]:
                if not m.get("begin") or not m.get("end") or not _meets_on(m, day):
                    continue
                start = datetime.combine(day, time.fromisoformat(m["begin"]), CAMPUS_TZ)
                end = datetime.combine(day, time.fromisoformat(m["end"]), CAMPUS_TZ)
                if end <= now:
                    continue
                occurrences.append({
                    "label": s["label"], "title": s["title"], "where": m.get("where"),
                    "start": start.astimezone(timezone.utc).isoformat(timespec="minutes"),
                    "time": _clock(start.time()),
                    "day": "Today" if offset == 0 else "Tomorrow" if offset == 1 else f"{day:%A}",
                    "in_progress": start <= now,
                })
    occurrences.sort(key=lambda o: o["start"])
    found = {s["crn"] for s in sections}
    return {
        "set_up": True,
        "term": term,
        "classes": [{"crn": s["crn"], "label": f'{s["label"]}-{s["section"]}' if s.get("section") else s["label"],
                     "title": s["title"], "instructor": s["instructor"],
                     "meetings": [_meeting_text(m) for m in s["meetings"]] or ["Time TBA"]}
                    for s in sorted(sections, key=lambda s: s["label"])],
        "missing": [c for c in crns if c not in found],
        "today": [o for o in occurrences if o["day"] == "Today"],
        "next": occurrences[0] if occurrences else None,
    }
