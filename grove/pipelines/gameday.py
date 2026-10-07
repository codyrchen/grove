"""Rebels schedules from calendar (.ics) feeds, like the "Download schedule" links on athletics sites.

GAMEDAY_CALENDARS lists the feeds as space-separated sport=url pairs:
    GAMEDAY_CALENDARS="football=https://.../football.ics baseball=https://.../baseball.ics"
"""

import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from ..config import CAMPUS_TZ

USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
KEEP_DAYS = 180

# "Football vs LSU", "Ole Miss at Georgia", "Baseball vs. Arkansas (DH)"
MATCHUP = re.compile(r"(?:^|\s)(vs\.?|versus|at|@)\s+(.+)$", re.I)
TV = re.compile(r"\b(TV|Network|Broadcast)\s*:\s*([^\n|]+)", re.I)


def calendars() -> list[tuple[str, str]]:
    out = []
    for pair in os.environ.get("GAMEDAY_CALENDARS", "").split():
        sport, _, url = pair.partition("=")
        if sport and url.startswith(("https://", "http://")):
            out.append((sport.lower(), url))
    return out


def unfold(text: str) -> list[str]:
    """iCalendar wraps long lines; a line starting with a space or tab continues the previous one."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
                 .replace("\;", ";").replace("\\\\", "\\")).strip()


def parse_when(params: str, value: str) -> tuple[str | None, bool]:
    """Returns (ISO start, all_day). All-day/TBA games keep just the date."""
    value = value.strip()
    if "VALUE=DATE" in params.upper() and "T" not in value:
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat(), True
        except ValueError:
            return None, False
    m = re.fullmatch(r"(\d{8})T(\d{4})(\d{2})?(Z?)", value)
    if not m:
        return None, False
    dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    if m.group(4):
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        tz = re.search(r"TZID=([^;:]+)", params)
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz.group(1)) if tz else CAMPUS_TZ)
        except Exception:
            dt = dt.replace(tzinfo=CAMPUS_TZ)
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes"), False


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
    games, event = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            event = {}
        elif line == "END:VEVENT" and event is not None:
            if "summary" in event and event.get("start"):
                opponent, home = matchup(event["summary"], event.get("location", ""))
                tv = TV.search(event.get("description", ""))
                games.append({
                    "sport": sport, "opponent": opponent, "home": home,
                    "start": event["start"], "all_day": event["all_day"],
                    "location": event.get("location") or None,
                    "tv": tv.group(2).strip() if tv else None,
                    "url": event.get("url"),
                })
            event = None
        elif event is not None and ":" in line:
            name, _, value = line.partition(":")
            key, _, params = name.partition(";")
            key = key.upper()
            if key == "SUMMARY":
                event["summary"] = unescape(value)
            elif key == "LOCATION":
                event["location"] = unescape(value)
            elif key == "DESCRIPTION":
                event["description"] = unescape(value)
            elif key == "URL" and value.startswith(("https://", "http://")):
                event["url"] = value.strip()
            elif key == "DTSTART":
                event["start"], event["all_day"] = parse_when(params, value)
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
