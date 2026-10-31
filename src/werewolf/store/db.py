"""One database engine for the app: SQLite for tests and local runs, Postgres in production."""

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from werewolf.store.tables import metadata

DEFAULT_URL = "sqlite:///data/app.db"


def clean_url(url: str) -> str:
    """The address as SQLAlchemy wants it. Quotes, spaces and a line ending around it (easy to paste
    in from a .env file or a dashboard) are dropped, and the driver is named for Postgres."""
    url = url.strip().strip("'\"").strip()
    if url.startswith("postgres://"):  # the form some hosts hand out
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def make_engine(url: str | None = None) -> Engine:
    """An engine for `url`, else `DATABASE_URL`, else the local file. Creates missing tables."""
    url = clean_url(url or os.environ.get("DATABASE_URL") or DEFAULT_URL)
    parsed = make_url(url)
    if parsed.drivername == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True)
    metadata.create_all(engine)
    return engine
