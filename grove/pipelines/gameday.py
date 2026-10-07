"""Rebels schedules from calendar (.ics) feeds, like the "Download schedule" links on athletics sites.

GAMEDAY_CALENDARS lists the feeds as space-separated sport=url pairs:
    GAMEDAY_CALENDARS="football=https://.../football.ics baseball=https://.../baseball.ics"
"""

import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .. import ics

USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
KEEP_DAYS = 180

# "Football vs LSU", "Ole Miss at Georgia", "Baseball vs. Arkansas (DH)"
MATCHUP = re.compile(r"(?:^|\s)(vs\.?|versus|at|@)\s+(.+)$", re.I)
TV = re.compile(r"\b(TV|Network|Broadcast)\s*:\s*([^\n|]+)", re.I)


def calendars() -> list[tuple[str, str]]:
    return ics.feeds(os.environ.get("GAMEDAY_CALENDARS", ""))


def matchup(summary: str, location: str) -> tuple[str, bool | None]:
    """('LSU', True) for a home game; home is None for a neutral site."""
    m = MATCHUP.search(summary)
    if not m:
        return summary, None
    opponent = re.sub(r"\s*\((?:DH|Doubleheader)\)\s*$", "", m.group(2), flags=re.I).strip(" .")
    if m.group(1).lower() in ("at", "@"):
        return opponent, False
    loc = location.lower()
    if not loc or "oxford" in loc:
        return opponent, True
    return opponent, None  # "vs" somewhere other than Oxford: neutral site


def parse(text: str, sport: str) -> list[dict]:
    games = []
    for e in ics.events(text):
        opponent, home = matchup(e["summary"], e.get("location", ""))
        tv = TV.search(e.get("description", ""))
        games.append({
            "sport": sport, "opponent": opponent, "home": home,
            "start": e["start"], "all_day": e["all_day"],
            "location": e.get("location") or None,
            "tv": tv.group(2).strip() if tv else None,
            "url": e.get("url"),
        })
    return games


def fetch(now: datetime | None = None) -> dict:
    feeds = calendars()
    if not feeds:
        raise RuntimeError("set GAMEDAY_CALENDARS to the schedule calendar links")
    now = now or datetime.now(timezone.utc)
    games, errors = [], []
    for sport, url in feeds:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            games.extend(parse(r.text, sport))
        except Exception as e:  # one bad feed shouldn't hide the others
            errors.append(f"{sport}: {e}")
    if not games:
        raise RuntimeError("no games found; " + "; ".join(errors))
    lo, hi = (now - timedelta(days=2)).isoformat(), (now + timedelta(days=KEEP_DAYS)).isoformat()
    games = [g for g in games if lo[:10] <= g["start"][:10] <= hi[:10]]
    games.sort(key=lambda g: g["start"])
    return {"games": games}
