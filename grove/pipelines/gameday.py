"""Rebels schedules: from ESPN's team schedule feeds by default, or from calendar (.ics) feeds
like the "Add to calendar" links on athletics sites, if GAMEDAY_CALENDARS lists them as
space-separated sport=url pairs:
    GAMEDAY_CALENDARS="football=https://.../football.ics baseball=https://.../baseball.ics"
"""

import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .. import ics
from ..config import CAMPUS_TZ
from . import scores

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


# Without GAMEDAY_CALENDARS, schedules come from ESPN's public team schedule feeds
# (the same unofficial source as live scores). Sport label -> ESPN path.
ESPN_SPORTS = {
    "football": "football/college-football",
    "basketball": "basketball/mens-college-basketball",
    "womens-basketball": "basketball/womens-college-basketball",
    "baseball": "baseball/college-baseball",
}


def espn_season(sport: str, today) -> int:
    """ESPN names seasons by the year they end: basketball 2026-27 is 2027, football 2026 is 2026."""
    if sport == "football":
        return today.year if today.month >= 3 else today.year - 1  # bowls run into January
    return today.year + 1 if today.month >= 8 else today.year     # winter/spring sports


def parse_espn(raw: dict, sport: str) -> list[dict]:
    games = []
    for event in raw.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        us = next((c for c in teams if scores._is_us(c.get("team") or {})), None)
        them = next((c for c in teams if c is not us), None)
        when = scores._when(event.get("date") or comp.get("date"))
        if not us or not them or when is None:
            continue
        if comp.get("timeValid") is False:  # time not announced yet ("TBA")
            start, all_day = when.astimezone(CAMPUS_TZ).date().isoformat(), True
        else:
            start, all_day = when.astimezone(timezone.utc).isoformat(timespec="minutes"), False
        venue = comp.get("venue") or {}
        city = (venue.get("address") or {}).get("city")
        tv = [b.get("media", {}).get("shortName") or (b.get("names") or [None])[0]
              for b in comp.get("broadcasts") or []]
        team = them.get("team") or {}
        games.append({
            "sport": sport,
            "opponent": team.get("location") or team.get("shortDisplayName") or team.get("displayName") or "TBA",
            "home": None if comp.get("neutralSite") else us.get("homeAway") == "home",
            "start": start, "all_day": all_day,
            "location": ", ".join(p for p in (venue.get("fullName"), city) if p) or None,
            "tv": next((t for t in tv if t), None),
            "url": None,
        })
    return games


def _from_espn(now: datetime) -> tuple[list[dict], list[str]]:
    games, errors = [], []
    today = now.astimezone(CAMPUS_TZ).date()
    for sport, path in ESPN_SPORTS.items():
        url = f"{scores.BASE}/{path}/teams/{scores.team_id()}/schedule"
        try:
            r = requests.get(url, params={"season": espn_season(sport, today)}, timeout=30,
                             headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            games.extend(parse_espn(r.json(), sport))
        except Exception as e:  # one sport failing shouldn't hide the others
            errors.append(f"{sport}: {e}")
    return games, errors


def _from_calendars(feeds) -> tuple[list[dict], list[str]]:
    games, errors = [], []
    for sport, url in feeds:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            games.extend(parse(r.text, sport))
        except Exception as e:  # one bad feed shouldn't hide the others
            errors.append(f"{sport}: {e}")
    return games, errors


def fetch(now: datetime | None = None) -> dict:
    """Calendar links from GAMEDAY_CALENDARS if set; otherwise ESPN's team schedules."""
    now = now or datetime.now(timezone.utc)
    feeds = calendars()
    games, errors = _from_calendars(feeds) if feeds else _from_espn(now)
    if not games:
        raise RuntimeError("no games found; " + "; ".join(errors))
    lo, hi = (now - timedelta(days=2)).isoformat(), (now + timedelta(days=KEEP_DAYS)).isoformat()
    games = [g for g in games if lo[:10] <= g["start"][:10] <= hi[:10]]
    games.sort(key=lambda g: g["start"])
    return {"games": games}
