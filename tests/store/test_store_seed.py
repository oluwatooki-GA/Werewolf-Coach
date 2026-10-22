"""The database: finished games, their tags and the coach's generations, loaded from the files."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from werewolf.agents.scripted import policy
from werewolf.cli import main
from werewolf.coach.history import CheckSummary, Generation, save_generation
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replay, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.store import games, make_engine, seed
from werewolf.store.tables import coach_generations, metadata
from werewolf.store.tables import games as games_table
from werewolf.store.tables import tags as tags_table
from werewolf.tagger.tags import Tag, TagFile, save_tags


def played(seed_number: int) -> GameLog:
    players = new_game(seed_number).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    return to_log(
        asyncio.run(play_game(seed_number, None, {p.name: policy(wolves) for p in players}))
    )


def save_game(folder: Path, log: GameLog) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{log.seed}-{abs(hash(log.to_json())) % 10**8}.json"
    path.write_bytes(log.to_json().encode("utf-8"))
    return path


def generation(number: int) -> Generation:
    return Generation(
        side="wolf", number=number, champion_before="wolf.accuse_early@2",
        champion_after="wolf.accuse_early@2", evidence="4 lost games", diagnosis="They rushed.",
        challenger_card=None, challenger_text="", check=CheckSummary(attempts=3, passed=False),
        champion_arm=None, challenger_arm=None, promote=False, decision="none played",
        coach_cost=Decimal("0.05"),
    )  # fmt: skip


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    games_dir, coach_dir = tmp_path / "games", tmp_path / "coach"
    for number in (1, 2, 3):
        path = save_game(games_dir / "e1", played(number))
        if number == 1:
            save_tags(
                path,
                TagFile(
                    model="m", tags=[Tag(line="R1-1", speaker="Ada", round=1, moves=("probe",))]
                ),
            )
    save_generation(generation(1), coach_dir)
    return games_dir, coach_dir


def count(engine, table) -> int:  # type: ignore[no-untyped-def]
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_seeding_loads_games_tags_and_generations_and_a_second_run_adds_nothing(
    tmp_path: Path, files: tuple[Path, Path]
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    first = seed(engine, *files)
    assert (first.games_added, first.tags_added, first.generations_added) == (3, 1, 1)
    assert [count(engine, t) for t in (games_table, tags_table, coach_generations)] == [3, 1, 1]
    second = seed(engine, *files)
    assert (second.games_added, second.tags_added, second.generations_added) == (0, 0, 0)
    assert second.games_existing == 3
    assert [count(engine, t) for t in (games_table, tags_table, coach_generations)] == [3, 1, 1]


def test_a_stored_log_reads_back_identical_and_still_replays_exactly(
    tmp_path: Path, files: tuple[Path, Path]
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    seed(engine, *files)
    originals = {
        p.read_text(encoding="utf-8") for p in files[0].rglob("*.json") if "tags" not in p.name
    }
    with engine.connect() as conn:
        ids = [row.id for row in conn.execute(select(games_table.c.id))]
        loaded = [games.load_game(conn, game_id) for game_id in ids]
    assert {log.to_json() for log in loaded} == originals
    assert all(replay(log).to_json() == log.to_json() for log in loaded)


def test_the_game_row_carries_the_columns_the_site_filters_on(
    tmp_path: Path, files: tuple[Path, Path]
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    seed(engine, *files)
    with engine.connect() as conn:
        row = conn.execute(select(games_table).where(games_table.c.seed == 1)).one()
    assert row.winner in ("Village", "Wolves") and row.rounds >= 1
    assert row.status == "finished" and row.source == "e1" and row.human_seat is None
    assert row.rule_version == "v2" and row.clean is True


def test_an_unreadable_game_is_skipped_and_named_not_fatal(
    tmp_path: Path, files: tuple[Path, Path]
) -> None:
    (files[0] / "e1" / "9-broken.json").write_text("{not json", encoding="utf-8")
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    report = seed(engine, *files)
    assert report.games_added == 3
    assert list(report.skipped) == [str(files[0] / "e1" / "9-broken.json")]


def test_the_schema_has_no_sql_that_only_sqlite_accepts() -> None:
    for table in metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_the_seed_command_loads_the_files_into_the_database(
    tmp_path: Path, files: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    args = [
        "app",
        "seed",
        "--database",
        url,
        "--games-dir",
        str(files[0]),
        "--coach-dir",
        str(files[1]),
    ]
    assert main(args) == 0
    assert "3 games added" in capsys.readouterr().out
    assert main(args) == 0
    assert "0 games added" in capsys.readouterr().out
