"""Live Rebels scores (football, basketball, baseball) from ESPN's public scoreboard feeds.

These feeds are unofficial (no key, used by many hobby apps) and could change without notice,
so everything here fails soft: if one breaks, the Game Day card just shows the schedule.

To be polite, ESPN is only asked about a game from an hour before it starts until it's final:
once a minute on our server, shared by every visitor. Otherwise nothing is fetched.
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from .. import db
from ..config import CAMPUS_TZ

BASE = "https://site.api.espn.com/apis/site/v2/sports"
USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
TEAM_ID = "145"            # Ole Miss on ESPN (same id in every sport); override with SCORES_TEAM_ID
TEAM_NAME = "Ole Miss"     # fallback match if the id ever changes
CHECK_BEFORE = timedelta(hours=1)
KEEP_FINAL = timedelta(hours=36)

# Schedule label (from GAMEDAY_CALENDARS) -> ESPN scoreboard path, its "groups" filter
# (all FBS / Division I games, not just the featured ones) and how long to keep checking.
SPORTS = {
    "football": ("football/college-football", "80", timedelta(hours=6)),
    "basketball": ("basketball/mens-college-basketball", "50", timedelta(hours=4)),
    "mbb": ("basketball/mens-college-basketball", "50", timedelta(hours=4)),
    "womens-basketball": ("basketball/womens-college-basketball", "50", timedelta(hours=4)),
    "wbb": ("basketball/womens-college-basketball", "50", timedelta(hours=4)),
    "baseball": ("baseball/college-baseball", None, timedelta(hours=6)),
}


def team_id() -> str:
    return os.environ.get("SCORES_TEAM_ID", TEAM_ID)


def _score(value) -> int | None:
    if isinstance(value, dict):  # some ESPN endpoints wrap scores: {"value": 24.0, "displayValue": "24"}
        value = value.get("value", value.get("displayValue"))
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _is_us(team: dict) -> bool:
    return str(team.get("id")) == team_id() or TEAM_NAME.lower() in (
        f'{team.get("location", "")} {team.get("displayName", "")}'.lower())


def _when(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def parse(raw: dict, sport: str = "football", near: datetime | None = None) -> dict | None:
    """Our game from a scoreboard response, or None if Ole Miss isn't in it.
    With `near`, picks the game starting closest to it (baseball doubleheaders)."""
    found = []
    for event in raw.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        us = next((c for c in teams if _is_us(c.get("team") or {})), None)
        them = next((c for c in teams if c is not us), None)
        if not us or not them:
            continue
        status = (comp.get("status") or event.get("status") or {}).get("type") or {}
        state = status.get("state")  # "pre", "in" or "post"
        ours, theirs = _score(us.get("score")), _score(them.get("score"))
        won = None
        if state == "post" and status.get("completed", True) and ours is not None and theirs is not None:
            won = ours > theirs if ours != theirs else None
        broadcasts = [n for b in comp.get("broadcasts") or [] for n in b.get("names") or []]
        them_team = them.get("team") or {}
        found.append({
            "sport": sport,
            "id": str(event.get("id")),
            "start": event.get("date"),
            "state": state if state in ("pre", "in", "post") else "pre",
            "detail": status.get("shortDetail") or status.get("detail") or "",
            "home": us.get("homeAway") == "home",
            "us": ours, "them": theirs,
            "opponent": them_team.get("location") or them_team.get("shortDisplayName")
                        or them_team.get("displayName") or "Opponent",
            "opponent_abbr": them_team.get("abbreviation"),
            "won": won,
            "tv": broadcasts[0] if broadcasts else None,
        })
    if not found:
        return None
    if near is not None:
        found.sort(key=lambda g: abs((_when(g["start"]) or near) - near))
    return found[0]


def _scheduled(conn: db.DB) -> list[dict]:
    row = db.load(conn, "gameday")
    games = (row and row["data"] or {}).get("games") or []
    return [g for g in games if g.get("sport") in SPORTS and not g.get("all_day")]


def stored_games(data: dict | None) -> dict:
    """{sport: game}. Also reads the older single-game format ({"game": ...})."""
    data = data or {}
    if "games" in data:
        return dict(data["games"])
    return {data["game"]["sport"] if "sport" in data["game"] else "football": data["game"]} if data.get("game") else {}


def fetch(conn: db.DB, now: datetime | None = None) -> dict | None:
    """Updates the games on now; returns None when there's nothing to do (no request is made then)."""
    now = now or datetime.now(timezone.utc)
    previous = db.load(conn, "scores")
    games = stored_games(previous and previous["data"])

    to_check = []
    for g in _scheduled(conn):
        start = datetime.fromisoformat(g["start"])
        path, groups, give_up = SPORTS[g["sport"]]
        if not (start - CHECK_BEFORE <= now <= start + give_up):
            continue
        last = games.get(g["sport"])
        last_start = _when(last and last.get("start"))
        if last and last["state"] == "post" and last_start and abs(last_start - start) < timedelta(hours=2):
            continue  # this game is already final
        to_check.append((g, start, path, groups))
    if not to_check:
        return None

    errors = []
    for g, start, path, groups in to_check:
        day = start.astimezone(CAMPUS_TZ).strftime("%Y%m%d")
        params = {"dates": day, "limit": "300"}
        if groups:
            params["groups"] = groups
        try:
            r = requests.get(f"{BASE}/{path}/scoreboard", params=params,
                             headers={"User-Agent": USER_AGENT}, timeout=15)
            r.raise_for_status()
            found = parse(r.json(), g["sport"], near=start)
        except Exception as e:  # one sport's feed failing shouldn't stop the others
            errors.append(f"{g['sport']}: {e}")
            continue
        if found is None:
            errors.append(f"{g['sport']}: Ole Miss game not found on ESPN's scoreboard for {day}")
            continue
        games[g["sport"]] = found
    if errors and len(errors) == len(to_check):
        raise RuntimeError("; ".join(errors))
    # Forget games old enough that nobody shows them any more.
    games = {s: x for s, x in games.items() if (_when(x.get("start")) or now) > now - KEEP_FINAL}
    return {"games": games}


fetch.needs_db = True
