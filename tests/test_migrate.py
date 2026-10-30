"""`app migrate` makes sure the tables exist, so a release can prepare the database."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from werewolf.cli import main

TABLES = {"games", "tags", "coach_generations", "play_sessions", "play_spend"}


def test_it_creates_the_tables_in_an_empty_database(
    tmp_path: Path,
    capsys: "pytest.CaptureFixture[str]",  # type: ignore[name-defined]  # noqa: F821
) -> None:
    url = f"sqlite:///{tmp_path / 'new.db'}"
    assert main(["app", "migrate", "--database", url]) == 0
    assert TABLES <= set(inspect(create_engine(url)).get_table_names())
    assert "tables ready" in capsys.readouterr().out


def test_it_can_be_run_again_and_keeps_what_is_there(tmp_path: Path) -> None:
    from werewolf.store.play import add_spend

    url = f"sqlite:///{tmp_path / 'again.db'}"
    assert main(["app", "migrate", "--database", url]) == 0
    with create_engine(url).begin() as conn:
        add_spend(conn, "2026-10-30", 0.5)
    assert main(["app", "migrate", "--database", url]) == 0
    with create_engine(url).connect() as conn:
        assert conn.exec_driver_sql("select spent from play_spend").scalar_one() == 0.5


def test_a_database_that_cannot_be_prepared_is_an_error_not_a_crash(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    assert main(["app", "migrate", "--database", f"sqlite:///{blocker / 'x.db'}"]) == 2
