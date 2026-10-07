"""Build the JSON each dashboard widget renders. Widgets only read the database (or compute),
so a slow or broken source never slows down or breaks the page."""

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import content, db
from .config import CAMPUS_TZ
from .pipelines.weather import SNOW_CODES, describe

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
STALE_AFTER = {"weather": 3 * 3600, "news": 12 * 3600, "gameday": 24 * 3600, "events": 12 * 3600}


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


def trivia_of_the_day(now: datetime | None = None, directory: Path | None = None) -> str | None:
    facts = [f["text"] for f in content.entries("trivia.json", directory) if f.get("text")]
    if not facts:
        return None
    today = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ).date()
    # Offset from the photo rotation so the pairings change.
    return facts[(today.toordinal() * 7) % len(facts)]


def current_moment(now: datetime | None = None, directory: Path | None = None) -> dict | None:
    """The campus moment happening today (Homecoming week, finals...), from moments.json."""
    today = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ).date()
    for m in content.entries("moments.json", directory):
        start, end = content.parse_date(m.get("start")), content.parse_date(m.get("end"))
        if start and end and start <= today <= end and m.get("message"):
            return {"message": m["message"], "mode": m.get("mode")}
    return None


def snowing(conn: db.DB) -> bool:
    """Snow in Oxford right now or in today's forecast."""
    row = db.load(conn, "weather")
    w = row and row["data"]
    if not w:
        return False
    return w.get("code") in SNOW_CODES or bool(w.get("days")) and w["days"][0].get("code") in SNOW_CODES


def countdowns(now: datetime | None = None, directory: Path | None = None) -> dict:
    """Upcoming academic dates from academic_calendar.json (personal countdowns live in the browser)."""
    today = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ).date()
    upcoming = []
    for e in content.entries("academic_calendar.json", directory):
        d = content.parse_date(e.get("date"))
        if d and e.get("name") and 0 <= (d - today).days <= 120:
            upcoming.append({"name": e["name"], "date": d.isoformat(), "days": (d - today).days})
    upcoming.sort(key=lambda e: e["date"])
    return {"academic": upcoming[:5]}


def square_feature(now: datetime | None = None, directory: Path | None = None) -> dict | None:
    """This week's featured Oxford Square business, rotating every Monday."""
    shops = [s for s in content.entries("square.json", directory) if s.get("name")]
    if not shops:
        return None
    today = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_TZ).date()
    s = shops[today.isocalendar().week % len(shops)]
    return {"name": s["name"], "blurb": s.get("blurb"), "deal": s.get("deal"),
            "url": _web_url(s.get("url"))}


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
            "credit": p.get("credit"),
            # Link the name to the photographer's page, or else to the photo's source page.
            "credit_url": _web_url(p.get("credit_url")) or _web_url(p.get("source_url")),
            "license": p.get("license"), "license_url": _web_url(p.get("license_url")),
            "resized": bool(p.get("resized"))}


def _web_url(url) -> str | None:
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


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


GAME_LENGTH = timedelta(hours=4)


def _game_start(g: dict) -> datetime:
    if g.get("all_day"):
        d = date.fromisoformat(g["start"][:10])
        return datetime(d.year, d.month, d.day, tzinfo=CAMPUS_TZ)
    return datetime.fromisoformat(g["start"])


SCORE_SHOWN_FOR = timedelta(hours=36)


def current_scores(conn: db.DB, now: datetime) -> list[dict]:
    """Live and just-finished games from ESPN that are recent enough to show: live ones first,
    then finals, newest first."""
    from .pipelines.scores import stored_games
    row = db.load(conn, "scores")
    shown = []
    for game in stored_games(row and row["data"]).values():
        try:
            start = datetime.fromisoformat(game["start"].replace("Z", "+00:00"))
        except (AttributeError, KeyError, ValueError):
            continue
        if start - timedelta(hours=1) <= now <= start + SCORE_SHOWN_FOR and game.get("state") != "pre":
            shown.append(game)
    shown.sort(key=lambda g: g["start"], reverse=True)   # newest first...
    shown.sort(key=lambda g: g["state"] != "in")         # ...with live games on top
    return shown


def kickoff_forecast(conn: db.DB, game: dict) -> dict | None:
    """The hourly forecast for a game's kickoff, once it's within the 5-day forecast."""
    if game.get("all_day") or game.get("home") is False:
        return None  # no time yet, or an away game (the forecast is for Oxford)
    row = db.load(conn, "weather")
    hours = (row and row["data"] or {}).get("forecast") or []
    kickoff = datetime.fromisoformat(game["start"]).astimezone(CAMPUS_TZ).strftime("%Y-%m-%dT%H:00")
    h = next((h for h in hours if h["t"] == kickoff), None)
    if not h:
        return None
    text, icon = describe(h["code"], bool(h["day"]))
    return {"temp": h["temp"], "text": text, "icon": icon, "rain": h["rain"]}


def gameday(conn: db.DB, now: datetime | None = None, directory: Path | None = None) -> dict:
    """Next Rebels games, plus today's and this week's football game for game-day mode."""
    out = stored(conn, "gameday", now)
    if out["data"] is None:
        out["empty"] = True  # hidden until GAMEDAY_CALENDARS is set up
        return out
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(CAMPUS_TZ).date()
    upcoming = []
    for g in out["data"].get("games", []):
        start = _game_start(g)
        end = start + (timedelta(days=1) if g.get("all_day") else GAME_LENGTH)
        if end > now:
            upcoming.append({**g, "local_date": start.astimezone(CAMPUS_TZ).date().isoformat(),
                             "live": start <= now and not g.get("all_day")})
    football = [g for g in upcoming if g["sport"] == "football"]
    if upcoming:
        upcoming[0] = {**upcoming[0], "forecast": kickoff_forecast(conn, upcoming[0])}
    info = content.load("gameday_info.json", {}, directory)
    info = info if isinstance(info, dict) else {}
    out["data"] = {
        "upcoming": upcoming[:4],
        "tips": [{"title": t["title"], "text": t.get("text"), "url": _web_url(t.get("url"))}
                 for t in info.get("tips", []) if isinstance(t, dict) and t.get("title")],
        "notes": (info.get("notes") or {}).get(upcoming[0]["local_date"]) if upcoming else None,
        "scores": current_scores(conn, now),
        "today": next((g for g in football if g["local_date"] == today.isoformat()), None),
        "this_week": next((g for g in football
                           if 0 < (date.fromisoformat(g["local_date"]) - today).days <= 6), None),
    }
    return out


EVENING = 16  # "tonight" starts at 4 p.m. in Oxford


def _event_window(e: dict) -> tuple[datetime, datetime]:
    if e.get("all_day"):
        d = date.fromisoformat(e["start"][:10])
        start = datetime(d.year, d.month, d.day, tzinfo=CAMPUS_TZ)
        return start, start + timedelta(days=1)
    start = datetime.fromisoformat(e["start"])
    end = datetime.fromisoformat(e["end"]) if e.get("end") else start + timedelta(hours=2)
    return start, max(end, start)


def tonight(conn: db.DB, now: datetime | None = None) -> dict:
    """Events still to come today (with tonight's first), then the next few days."""
    out = stored(conn, "events", now)
    if out["data"] is None:
        out["empty"] = True
        return out
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(CAMPUS_TZ).date()
    today_list, later = [], []
    for e in out["data"].get("events", []):
        start, end = _event_window(e)
        if end <= now:
            continue
        local = start.astimezone(CAMPUS_TZ)
        item = {**e, "local_date": local.date().isoformat(),
                "evening": not e.get("all_day") and local.hour >= EVENING, "happening": start <= now}
        if local.date() <= today:
            today_list.append(item)
        elif (local.date() - today).days <= 3:
            later.append(item)
    # Tonight's events first, then the rest of today; all-day events last.
    today_list.sort(key=lambda e: (e["all_day"], not e["evening"], e["start"]))
    out["data"] = {"today": today_list[:8], "soon": later[:8],
                   "food_count": sum(e["food"] for e in today_list + later)}
    out["empty"] = not (today_list or later)
    return out


DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _clock_label(t: datetime) -> str:
    """9:00 -> '9 AM', 13:30 -> '1:30 PM'"""
    hour = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{hour} {ampm}" if t.minute == 0 else f"{hour}:{t.minute:02d} {ampm}"


def _ranges_on(place: dict, day: date) -> list[tuple[datetime, datetime]]:
    """Opening windows that start on `day`, as campus-time datetimes. '20:00-02:00' runs past midnight."""
    if day.isoformat() in (place.get("closed") or []):
        return []
    special = place.get("special") or {}
    ranges = special.get(day.isoformat(), (place.get("hours") or {}).get(DAY_KEYS[day.weekday()], []))
    out = []
    for r in ranges if isinstance(ranges, list) else []:
        try:
            a, b = r.split("-")
            start = datetime.combine(day, datetime.strptime(a.strip(), "%H:%M").time(), CAMPUS_TZ)
            end = datetime.combine(day, datetime.strptime(b.strip(), "%H:%M").time(), CAMPUS_TZ)
        except (ValueError, AttributeError):
            continue
        if end <= start:
            end += timedelta(days=1)
        out.append((start, end))
    return out


def dining_status(place: dict, now: datetime) -> dict:
    local = now.astimezone(CAMPUS_TZ)
    windows = []
    for offset in (-1, 0, 1, 2, 3, 4, 5, 6, 7):  # yesterday's late-night hours can still be open
        windows += _ranges_on(place, local.date() + timedelta(days=offset))
    windows.sort()
    current = next((w for w in windows if w[0] <= local < w[1]), None)
    if current:
        mins = int((current[1] - local).total_seconds() // 60)
        text = f"Closes in {mins} min" if mins < 60 else f"Open until {_clock_label(current[1])}"
        return {"open": True, "text": text, "closing_soon": mins < 60, "sort": current[1].isoformat()}
    nxt = next((w for w in windows if w[0] > local), None)
    if not nxt:
        return {"open": False, "text": "Closed", "closing_soon": False, "sort": "9"}
    days = (nxt[0].date() - local.date()).days
    when = (_clock_label(nxt[0]) if days == 0 else f"tomorrow {_clock_label(nxt[0])}" if days == 1
            else f"{nxt[0]:%A} {_clock_label(nxt[0])}")
    return {"open": False, "text": f"Opens {when}", "closing_soon": False, "sort": "1" + nxt[0].isoformat()}


def dining(now: datetime | None = None, directory: Path | None = None) -> dict:
    places = [p for p in content.entries("dining.json", directory) if p.get("name")]
    if not places:
        return {"data": None, "empty": True}
    now = now or datetime.now(timezone.utc)
    rows = []
    for p in places:
        st = dining_status(p, now)
        rows.append({"name": p["name"], "area": p.get("area"), "menu_url": _web_url(p.get("menu_url")), **st})
    # Open places first (closing soonest first), then by when they open.
    rows.sort(key=lambda r: (not r["open"], r.pop("sort")))
    late = now.astimezone(CAMPUS_TZ).hour >= 21 or now.astimezone(CAMPUS_TZ).hour < 4
    return {"data": {"places": rows, "open_count": sum(r["open"] for r in rows), "late_night": late}}


def build(conn: db.DB, name: str) -> dict:
    if name == "greeting":
        return {"data": {**greeting(), "moment": current_moment(), "trivia": trivia_of_the_day(),
                         "snow": snowing(conn)}}
    if name == "countdowns":
        return {"data": countdowns()}
    if name == "square":
        feature = square_feature()
        return {"data": feature, "empty": feature is None}
    if name == "photo":
        return {"data": photo_of_the_day()}
    if name == "gameday":
        return gameday(conn)
    if name == "tonight":
        return tonight(conn)
    if name == "dining":
        return dining()
    if name == "classes":
        # Filled in by the browser from /api/classes; hidden until a term is set.
        return {"data": None, "personal": True, "empty": not os.environ.get("GROVE_TERM")}
    if name == "links":
        return {"data": {"links": QUICK_LINKS}}
    return stored(conn, name)


# id -> title, in the default order. Columns are filled left to right.
WIDGETS = {
    "gameday": "Game Day",
    "classes": "My Classes",
    "weather": "Weather",
    "dining": "Dining Open Now",
    "tonight": "Tonight in Oxford",
    "countdowns": "Countdowns",
    "news": "Campus News",
    "links": "Quick Links",
    "square": "On the Square",
}

# Widgets each kind of visitor starts with (they can turn any on or off later).
ROLES = {
    "student": ["gameday", "classes", "weather", "dining", "tonight", "countdowns", "news", "links", "square"],
    "fan": ["gameday", "weather", "tonight", "countdowns", "news", "square"],
    "alumni": ["gameday", "weather", "tonight", "countdowns", "news", "square"],
}
