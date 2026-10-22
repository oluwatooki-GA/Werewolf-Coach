"""Load what the experiments produced (game logs, tag files, coach generations) into the database.
Safe to run again: anything already there is left alone."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine, insert, select

from werewolf.coach.history import load_history
from werewolf.engine.log import GameLog
from werewolf.store import games
from werewolf.store.tables import coach_generations
from werewolf.tagger.tags import game_files, load_tags

SIDES = ("wolf", "villager")


@dataclass
class SeedReport:
    games_added: int = 0
    games_existing: int = 0
    tags_added: int = 0
    generations_added: int = 0
    skipped: dict[str, str] = field(default_factory=dict)  # path -> why it was left out


def seed(engine: Engine, games_dir: Path, coach_dir: Path) -> SeedReport:
    report = SeedReport()
    with engine.begin() as conn:
        for path in game_files([str(games_dir)]) if games_dir.is_dir() else []:
            try:
                log = GameLog.from_json(path.read_text(encoding="utf-8"))
                tagfile = load_tags(path)
            except (OSError, ValueError, ValidationError) as exc:
                report.skipped[str(path)] = str(exc).splitlines()[0]
                continue
            id_ = games.game_id(log)
            if games.has_game(conn, id_):
                report.games_existing += 1
            else:
                source = path.parent.relative_to(games_dir).as_posix()
                games.add_game(conn, log, source="" if source == "." else source)
                report.games_added += 1
            if tagfile is not None and games.add_tags(conn, id_, tagfile):
                report.tags_added += 1
        for side in SIDES:
            for generation in load_history(side, coach_dir):
                known = conn.execute(
                    select(coach_generations.c.side).where(
                        coach_generations.c.side == side,
                        coach_generations.c.number == generation.number,
                    )
                ).first()
                if known is None:
                    conn.execute(
                        insert(coach_generations).values(
                            side=side,
                            number=generation.number,
                            record=generation.model_dump_json(),
                        )  # fmt: skip
                    )
                    report.generations_added += 1
    return report
