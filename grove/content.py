"""Hand-edited content in grove/data/*.json: academic dates, campus moments, trivia, Square features...

Edit the files and redeploy; no code changes needed. A missing or broken file counts as empty,
so a typo can't take the site down.
"""

import json
import os
from datetime import date
from pathlib import Path

DATA_DIR = Path(os.environ.get("GROVE_DATA_DIR") or Path(__file__).parent / "data")


def load(name: str, default=None, directory: Path | None = None):
    try:
        return json.loads(((directory or DATA_DIR) / name).read_text())
    except (FileNotFoundError, ValueError):
        return [] if default is None else default


def parse_date(value) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def entries(name: str, directory: Path | None = None) -> list[dict]:
    """A JSON list of objects; anything else in the file is ignored."""
    data = load(name, [], directory)
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
