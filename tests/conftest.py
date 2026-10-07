import os

import pytest

from grove import db


@pytest.fixture(params=["sqlite", "postgres"])
def database(request, tmp_path):
    """A fresh database URL. Postgres runs only when TEST_DATABASE_URL is set."""
    if request.param == "sqlite":
        return str(tmp_path / "test.db")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to also test against Postgres")
    conn = db.connect(url)
    conn.execute("DELETE FROM widget_data")
    conn.execute("DELETE FROM class_sections")
    conn.close()
    return url


@pytest.fixture
def conn(database):
    c = db.connect(database)
    yield c
    c.close()
