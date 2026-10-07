"""A small reader for iCalendar (.ics) feeds: athletics schedules, campus and Oxford event calendars."""

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .config import CAMPUS_TZ


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
    """Returns (ISO time in UTC, all_day). All-day/TBA entries keep just the date."""
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


def events(text: str) -> list[dict]:
    """Every VEVENT with a title and start: summary, start, all_day, end, location, description, url."""
    out, event = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            event = {}
        elif line == "END:VEVENT" and event is not None:
            if event.get("summary") and event.get("start"):
                out.append(event)
            event = None
        elif event is not None and ":" in line:
            name, _, value = line.partition(":")
            key, _, params = name.partition(";")
            key = key.upper()
            if key in ("SUMMARY", "LOCATION", "DESCRIPTION"):
                event[key.lower()] = unescape(value)
            elif key == "URL" and value.strip().startswith(("https://", "http://")):
                event["url"] = value.strip()
            elif key == "DTSTART":
                event["start"], event["all_day"] = parse_when(params, value)
            elif key == "DTEND":
                event["end"], _ = parse_when(params, value)
    return out


def feeds(env_value: str) -> list[tuple[str, str]]:
    """'football=https://a.ics baseball=https://b.ics' -> [('football', 'https://a.ics'), ...]"""
    out = []
    for pair in env_value.split():
        label, _, url = pair.partition("=")
        if label and url.startswith(("https://", "http://")):
            out.append((label.lower(), url))
    return out
