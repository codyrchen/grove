"""Live Rebels football scores from ESPN's public scoreboard feed.

This feed is unofficial (no key, used by many hobby apps) and could change without notice,
so everything here fails soft: if it breaks, the Game Day card just shows the schedule.

To be polite, ESPN is only asked on game days, from an hour before kickoff until the game
is final: once a minute on our server, shared by every visitor. Otherwise nothing is fetched.
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from .. import db
from ..config import CAMPUS_TZ

URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
USER_AGENT = "Grove/0.1 (Ole Miss student dashboard)"
TEAM_ID = "145"            # Ole Miss on ESPN; override with SCORES_TEAM_ID
TEAM_NAME = "Ole Miss"     # fallback match if the id ever changes
CHECK_BEFORE = timedelta(hours=1)
GIVE_UP_AFTER = timedelta(hours=6)    # stop checking a game this long after kickoff
KEEP_FINAL = timedelta(hours=36)      # show "Final: W 31-24" this long after kickoff


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


def parse(raw: dict) -> dict | None:
    """Our game from a scoreboard response, or None if Ole Miss isn't playing in it."""
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
        return {
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
        }
    return None


def _football_games(conn: db.DB) -> list[dict]:
    row = db.load(conn, "gameday")
    games = (row and row["data"] or {}).get("games") or []
    return [g for g in games if g.get("sport") == "football" and not g.get("all_day")]


def fetch(conn: db.DB, now: datetime | None = None) -> dict | None:
    """Returns the latest game, or None when there's nothing to do (no request is made then)."""
    now = now or datetime.now(timezone.utc)
    previous = db.load(conn, "scores")
    last = (previous and previous["data"] or {}).get("game")

    live_window = [g for g in _football_games(conn)
                   if datetime.fromisoformat(g["start"]) - CHECK_BEFORE <= now
                   <= datetime.fromisoformat(g["start"]) + GIVE_UP_AFTER]
    if not live_window:
        return None
    game = live_window[0]
    if last and last.get("state") == "post" and last.get("start") and \
            abs(datetime.fromisoformat(last["start"].replace("Z", "+00:00")) -
                datetime.fromisoformat(game["start"])) < timedelta(hours=3):
        return None  # already final; nothing more to check

    day = datetime.fromisoformat(game["start"]).astimezone(CAMPUS_TZ).strftime("%Y%m%d")
    r = requests.get(URL, params={"dates": day, "groups": "80", "limit": "300"},
                     headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    found = parse(r.json())
    if found is None:
        raise RuntimeError(f"Ole Miss game not found on ESPN's scoreboard for {day}")
    return {"game": found}


fetch.needs_db = True
