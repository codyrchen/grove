"""Refresh widget data from each source on its own schedule.

    python -m grove.refresh --once            # every pipeline, once
    python -m grove.refresh --once weather    # just one
    python -m grove.refresh                   # loop forever (what start.sh runs)
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

from . import db
from .config import database_url, load_env
from .pipelines import gameday, news, weather

# name -> (fetch function, seconds between refreshes)
PIPELINES = {
    "weather": (weather.fetch, 30 * 60),
    "news": (news.fetch, 60 * 60),
    "gameday": (gameday.fetch, 3 * 60 * 60),
}


def run(conn: db.DB, name: str) -> bool:
    fetch, _ = PIPELINES[name]
    try:
        data = fetch()
    except Exception as e:
        db.save_error(conn, name, f"{type(e).__name__}: {e}")
        print(f"! {name} failed: {e}  (keeping the last good data)")
        return False
    db.save_data(conn, name, data)
    print(f"{name}: updated")
    return True


def due(conn: db.DB, name: str, now: datetime | None = None) -> bool:
    last = db.last_attempt(conn, name)
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - datetime.fromisoformat(last) >= timedelta(seconds=PIPELINES[name][1])


def main(argv=None):
    load_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("names", nargs="*", help=f"pipelines to run ({', '.join(PIPELINES)})")
    p.add_argument("--once", action="store_true", help="run once and exit")
    args = p.parse_args(argv)
    names = args.names or list(PIPELINES)
    unknown = set(names) - set(PIPELINES)
    if unknown:
        p.error(f"unknown pipeline: {', '.join(sorted(unknown))}")
    conn = db.connect(database_url())
    if args.once:
        results = [run(conn, n) for n in names]
        raise SystemExit(0 if all(results) else 1)
    while True:
        for n in names:
            if due(conn, n):
                run(conn, n)
        time.sleep(60)


if __name__ == "__main__":
    main()
