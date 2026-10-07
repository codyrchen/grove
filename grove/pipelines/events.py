"""Campus and Oxford events from calendar (.ics) feeds, for the "Tonight in Oxford" card.

EVENTS_CALENDARS lists the feeds as space-separated label=url pairs:
    EVENTS_CALENDARS="campus=https://.../events.ics oxford=https://.../calendar.ics"
"""

import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .. import ics

USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
KEEP_DAYS = 14
MAX_EVENTS = 300

FOOD = re.compile(
    r"\b(free food|pizza|lunch|dinner|breakfast|brunch|snacks?|refreshments|cookies|donuts?|"
    r"doughnuts|bbq|barbecue|cookout|crawfish|tacos?|ice cream|food truck|treats|catered|"
    r"food will be provided)\b", re.I)


def calendars() -> list[tuple[str, str]]:
    return ics.feeds(os.environ.get("EVENTS_CALENDARS", ""))


def has_food(*texts: str) -> bool:
    return any(FOOD.search(t or "") for t in texts)


def parse(text: str, source: str) -> list[dict]:
    out = []
    for e in ics.events(text):
        desc = e.get("description", "")
        out.append({
            "title": e["summary"][:160],
            "start": e["start"], "end": e.get("end"), "all_day": e["all_day"],
            "location": (e.get("location") or "")[:120] or None,
            "url": e.get("url"),
            "source": source,
            "food": has_food(e["summary"], desc),
        })
    return out


def fetch(now: datetime | None = None) -> dict:
    feeds = calendars()
    if not feeds:
        raise RuntimeError("set EVENTS_CALENDARS to campus and Oxford calendar links")
    now = now or datetime.now(timezone.utc)
    found, errors = [], []
    for source, url in feeds:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            found.extend(parse(r.text, source))
        except Exception as e:  # one bad feed shouldn't hide the others
            errors.append(f"{source}: {e}")
    if not found and errors:
        raise RuntimeError("; ".join(errors))
    lo = (now - timedelta(days=1)).isoformat()[:10]
    hi = (now + timedelta(days=KEEP_DAYS)).isoformat()[:10]
    keep, seen = [], set()
    for e in sorted(found, key=lambda e: e["start"]):
        key = (e["title"].lower(), e["start"])
        if lo <= e["start"][:10] <= hi and key not in seen:  # same event in two feeds
            seen.add(key)
            keep.append(e)
    return {"events": keep[:MAX_EVENTS]}
