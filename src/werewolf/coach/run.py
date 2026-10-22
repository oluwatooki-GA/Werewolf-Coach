"""Run the coach for several generations in a row, and pick up where a stopped run left off.

Each generation reads the games it is given plus the games the earlier generations played, and
tests on seeds nobody has used yet, so what the coach reads and what it is tested on never share
a game. A run that stops (cap, rate limit) saves nothing for the generation in progress.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from werewolf.coach.evidence import SIDES
from werewolf.coach.graph import run_generation
from werewolf.coach.history import COACH_DIR, Generation, load_history
from werewolf.coach.steps import CoachError
from werewolf.engine.log import GameLog
from werewolf.engine.state import Settings
from werewolf.llm.client import LLMClient
from werewolf.strategies.cards import load_card
from werewolf.tagger.tags import TagFile, game_files, load_tags

START_CHAMPION = {"wolf": "wolf.accuse_early", "villager": "villager.quiet_observer"}

Game = tuple[GameLog, TagFile | None]


@dataclass(frozen=True)
class CoachPlan:
    side: str
    generations: int  # how many generations there should be in all, counting finished ones
    games: int  # games per arm
    first_seed: int
    champion: str  # the card to start from (ignored once a generation has been saved)
    evidence: list[str]  # folders or files of earlier games the coach reads
    player_model: str
    coach_model: str
    check_model: str
    parallel: int = 3


def load_games(paths: Sequence[str], skip_seeds: set[int]) -> list[Game]:
    """The games in these files and folders, with their tags if they have any. A game whose seed
    is about to be tested is left out. An unreadable file is an error: stop rather than guess."""
    games: list[Game] = []
    for path in game_files(list(paths)):
        try:
            log = GameLog.from_json(path.read_text(encoding="utf-8"))
            tags = load_tags(path)
        except (OSError, ValueError, ValidationError) as exc:
            raise CoachError(f"cannot read {path}: {exc}") from exc
        if log.seed not in skip_seeds:
            games.append((log, tags))
    return games


def check_plan(plan: CoachPlan, root: Path = COACH_DIR) -> str:
    """Everything that can be wrong before the first model call. Returns the card to start the
    next generation from, or raises ValueError saying what is wrong."""
    if plan.side not in SIDES:
        raise ValueError(f"unknown side '{plan.side}'; use one of: {', '.join(SIDES)}")
    if plan.games < 1 or plan.generations < 1:
        raise ValueError("--games and --generations must be at least 1")
    saved = load_history(plan.side, root)
    start = saved[-1].champion_after.split("@")[0] if saved else plan.champion
    card = load_card(start)  # raises ValueError for an unknown card
    if card.role is not SIDES[plan.side][0]:
        raise ValueError(
            f"{card.id} is a {card.role.value} card; the {plan.side} side needs another"
        )
    missing = [p for p in plan.evidence if not Path(p).exists()]
    if missing or not any(game_files([p]) for p in plan.evidence):
        raise ValueError(
            f"no games found in: {', '.join(missing or plan.evidence) or '--evidence'}"
        )
    return start


def seeds_for(plan: CoachPlan, number: int) -> list[int]:
    start = plan.first_seed + (number - 1) * plan.games
    return list(range(start, start + plan.games))


async def run_coach(
    coach: LLMClient,
    players: LLMClient,
    plan: CoachPlan,
    *,
    settings: Settings,
    root: Path = COACH_DIR,
    say: Callable[[str], None] = print,
) -> list[Generation]:
    """Finish generations up to `plan.generations`. Returns the ones run now (not earlier ones)."""
    start = check_plan(plan, root)
    arm_games = root / plan.side / "games"
    done: list[Generation] = []
    champion = start
    for number in range(len(load_history(plan.side, root)) + 1, plan.generations + 1):
        seeds = seeds_for(plan, number)
        read_from = [*plan.evidence, *([str(arm_games)] if arm_games.exists() else [])]
        games = load_games(read_from, set(seeds))
        say(
            f"generation {number}: reading {len(games)} games, "
            f"testing on seeds {seeds[0]}-{seeds[-1]}"
        )
        generation = await run_generation(
            coach,
            player_client=players,
            side=plan.side,
            number=number,
            champion=champion,
            games=games,
            seeds=seeds,
            player_model=plan.player_model,
            coach_model=plan.coach_model,
            check_model=plan.check_model,
            settings=settings,
            data_dir=arm_games,
            root=root,
            parallel=plan.parallel,
        )
        say(f"generation {number}: {generation.decision} (${generation.cost:.4f})")
        champion = generation.champion_after.split("@")[0]
        done.append(generation)
    return done
