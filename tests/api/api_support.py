"""A small database of known games for the API tests."""

import asyncio
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine

from werewolf.agents.scripted import policy
from werewolf.coach.history import CheckSummary, Generation, save_generation
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.store import make_engine, seed
from werewolf.tagger.tags import Tag, TagFile, save_tags

WOLF_CARD, VILLAGER_CARD = "wolf.accuse_early@2", "villager.quiet_observer@2"
PLAY_CARDS = {
    Role.WEREWOLF: "wolf.lie_low",
    Role.VILLAGER: "villager.track_votes",
    Role.SEER: "seer.reveal_now",
    Role.DOCTOR: "doctor.protect_seer",
}


def play_body(seed: int = 3, **changes: str) -> dict[str, object]:
    """A POST /play body: each seat of the seed's table on its role's usual card, then `changes`."""
    cards = {p.name: PLAY_CARDS[p.role] for p in new_game(seed).players}
    return {"seed": seed, "cards": {**cards, **changes}}


def seat_of(role: Role, n: int = 0, seed: int = 3) -> str:
    """The name of the n-th seat with this role at the seed's table."""
    return [p.name for p in new_game(seed).players if p.role is role][n]


def played(number: int, wolf_card: str | None = None, villager_card: str | None = None) -> GameLog:
    players = new_game(number).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    log = to_log(asyncio.run(play_game(number, None, {p.name: policy(wolves) for p in players})))
    cards = {}
    for p in players:
        if p.role is Role.WEREWOLF and wolf_card:
            cards[p.name] = wolf_card
        if p.role is Role.VILLAGER and villager_card:
            cards[p.name] = villager_card
    settings = log.settings.model_copy(update={"cards": cards})
    return log.model_copy(update={"settings": settings})


def generation(number: int) -> Generation:
    return Generation(
        side="wolf", number=number, champion_before=WOLF_CARD, champion_after=WOLF_CARD,
        evidence="4 lost games", diagnosis="They rushed.", challenger_card=None,
        challenger_text="", check=CheckSummary(attempts=3, passed=False), champion_arm=None,
        challenger_arm=None, promote=False, decision="none played", coach_cost=Decimal("0.05"),
    )  # fmt: skip


def build(
    tmp_path: Path,
    logs: list[GameLog],
    tagged: tuple[int, ...] = (),
    tagfile: TagFile | None = None,
) -> Engine:
    """Write the games (and tags for the seeds in `tagged`) to files and seed a database."""
    games_dir, coach_dir = tmp_path / "games", tmp_path / "coach"
    games_dir.mkdir(parents=True)
    for index, log in enumerate(logs):
        path = games_dir / f"{log.seed}-{index}.json"
        path.write_bytes(log.to_json().encode("utf-8"))
        if log.seed in tagged:
            tag = Tag(line="R1-1", speaker=log.players[0].name, round=1, moves=("probe",))
            save_tags(path, tagfile or TagFile(model="m", tags=[tag]))
    save_generation(generation(1), coach_dir)
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    seed(engine, games_dir, coach_dir)
    return engine
