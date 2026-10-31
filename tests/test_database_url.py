"""A database address pasted with quotes or a line ending still works."""

from pathlib import Path

import pytest

from werewolf.store import make_engine


@pytest.mark.parametrize("wrap", ["{}", "'{}'", '"{}"', "{}\r", "'{}'\r\n", "  {}  ", '"{}"\n'])
def test_quotes_spaces_and_line_endings_around_the_address_are_ignored(
    tmp_path: Path, wrap: str
) -> None:
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine = make_engine(wrap.format(url))
    assert engine.url.database == str(tmp_path / "a.db")


def test_the_environment_variable_gets_the_same_care(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"'sqlite:///{tmp_path / 'env.db'}'\r")
    assert make_engine().url.database == str(tmp_path / "env.db")


def test_a_postgres_address_in_quotes_is_still_given_the_psycopg_driver() -> None:
    from werewolf.store.db import clean_url

    cleaned = clean_url("'postgresql://user:pass@host/db?sslmode=require'\r")
    assert cleaned == "postgresql+psycopg://user:pass@host/db?sslmode=require"
    assert clean_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
