"""Build the JSON each dashboard widget renders. Widgets only read the database (or compute),
so a slow or broken source never slows down or breaks the page."""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from . import db
from .config import CAMPUS_TZ

QUICK_LINKS = [
    {"label": "myOleMiss", "url": "https://my.olemiss.edu", "icon": "person-badge", "color": "#ce1126"},
    {"label": "Blackboard", "url": "https://blackboard.olemiss.edu", "icon": "easel2", "color": "#1f3260"},
    {"label": "Email", "url": "https://outlook.office.com/mail/", "icon": "envelope-fill", "color": "#0a64c8"},
    {"label": "Register", "url": "https://experience.elluciancloud.com/umsaasproduction",
     "icon": "calendar-plus-fill", "color": "#2e8b57"},
    {"label": "RebelSnatch", "url": "https://rebelsnatch.com", "icon": "lightning-charge-fill", "color": "#e0a100"},
    {"label": "Libraries", "url": "https://libraries.olemiss.edu", "icon": "book-fill", "color": "#6a4fb3"},
]

# Data older than this many seconds is flagged as stale (the source has been failing).
STALE_AFTER = {"weather": 3 * 3600, "news": 12 * 3600}


def time_ago(iso: str | None, now: datetime | None = None) -> str | None:
    if not iso:
        return None
    now = now or datetime.now(timezone.utc)
    seconds = (now - datetime.fromisoformat(iso)).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    return f"{int(seconds // 86400)} days ago"


def _env_date(name: str) -> date | None:
    try:
        return date.fromisoformat(os.environ.get(name, ""))
    except ValueError:
        return None


def greeting(now: datetime | None = None) -> dict:
    local = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ)
    hour = local.hour
    hello = ("Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17
             else "Good evening" if 17 <= hour < 22 else "Good night")
    out = {"hello": hello, "date": f"{local:%A, %B} {local.day}, {local.year}",
           "semester_week": None}
    start, end = _env_date("SEMESTER_START"), _env_date("SEMESTER_END")
    today = local.date()
    if start and end and start <= today <= end:
        out["semester_week"] = (today - start).days // 7 + 1
        out["days_left"] = (end - today).days
    return out


PHOTOS_DIR = Path(__file__).parent / "static" / "photos"


def photos(directory: Path = PHOTOS_DIR) -> list[dict]:
    """Campus photos listed in photos.json whose files exist."""
    try:
        entries = json.loads((directory / "photos.json").read_text())
    except (FileNotFoundError, ValueError):
        return []
    return [p for p in entries
            if isinstance(p, dict) and p.get("file") and (directory / p["file"]).is_file()
            and "/" not in p["file"]]


def photo_of_the_day(now: datetime | None = None, directory: Path = PHOTOS_DIR) -> dict | None:
    """Everyone sees the same photo each day; it changes at midnight in Oxford."""
    available = photos(directory)
    if not available:
        return None
    today = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ).date()
    p = available[today.toordinal() % len(available)]
    return {"url": f"/static/photos/{p['file']}", "place": p.get("place"),
            "credit": p.get("credit"), "credit_url": p.get("credit_url")}


def stored(conn: db.DB, name: str, now: datetime | None = None) -> dict:
    row = db.load(conn, name)
    if row is None or row["data"] is None:
        return {"data": None, "updated": None, "updated_ago": None, "stale": False,
                "message": "Loading for the first time. Check back in a minute."}
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(row["fetched_at"])).total_seconds()
    return {"data": row["data"], "updated": row["fetched_at"],
            "updated_ago": time_ago(row["fetched_at"], now),
            "stale": age > STALE_AFTER.get(name, 6 * 3600)}


def build(conn: db.DB, name: str) -> dict:
    if name == "greeting":
        return {"data": greeting()}
    if name == "photo":
        return {"data": photo_of_the_day()}
    if name == "links":
        return {"data": {"links": QUICK_LINKS}}
    return stored(conn, name)


# id -> title, in the default order. Columns are filled left to right.
WIDGETS = {
    "weather": "Weather",
    "news": "Campus News",
    "links": "Quick Links",
}
