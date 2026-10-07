"""Settings read from the environment (and an optional .env file for local runs)."""

import os
from zoneinfo import ZoneInfo

CAMPUS_TZ = ZoneInfo("America/Chicago")
# Oxford, MS (the Lyceum)
OXFORD_LAT, OXFORD_LON = 34.3651, -89.5381


def load_env(path: str = ".env"):
    """Load KEY=VALUE lines into os.environ (existing variables win)."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def database_url() -> str:
    """Postgres URL on Railway; a local SQLite file otherwise."""
    return os.environ.get("DATABASE_URL", "grove.db")


def secret_key() -> str:
    return os.environ.get("SECRET_KEY", "dev-only-change-me")


def base_url() -> str:
    return os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
