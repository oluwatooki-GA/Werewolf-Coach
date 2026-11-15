"""The arena: a champion card and a challenger card play the same seeds, and a plain rule decides
whether the champion changes.

Only one side's card differs between two arms. The other side plays the default card, so a
difference in wins comes from the card being tested (plus the noise of model words, which is why
the rule needs a large gap).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Literal

from werewolf.coach.evidence import SIDES
from werewolf.engine.log import GameLog
from werewolf.engine.state import Settings
from werewolf.llm.client import LLMClient
from werewolf.runner import run_batch
from werewolf.runtime import default_max_tokens
from werewolf.tagger.adherence import wilson

MIN_GAP = Fraction(3, 10)  # DESIGN 6.1: under about 30 points is "not clear yet"


@dataclass
class Arm:
    card: str
    side: str
    seeds: list[int]  # the seeds that were asked for
    wins: int  # games the tested side won
    games: int  # games that finished
    clean: bool  # every finished game needed no fallback, and all of them finished
    cost: Decimal
    logs: list[GameLog] = field(default_factory=list)
    stopped: str | None = None  # why the arm ended early (spending cap, rate limit)

    @property
    def rate(self) -> Fraction:
        return Fraction(self.wins, self.games) if self.games else Fraction(0)

    def describe(self) -> str:
        if not self.games:
            return "no games"
        low, high = wilson(self.wins, self.games)
        return f"{self.wins}/{self.games} ({100 * low:.0f}-{100 * high:.0f}%)"


@dataclass(frozen=True)
class Verdict:
    promote: bool
    reason: str


async def play_arm(
    client: LLMClient,
    model: str,
    side: Literal["wolf", "villager"] | str,
    card_id: str,
    seeds: list[int],
    *,
    settings: Settings,
    data_dir: Path,
    parallel: int = 3,
) -> Arm:
    """Play every seed with this card for the side and the default card for everyone else."""
    role, team = SIDES[side]
    report = await run_batch(
        client,
        model,
        seeds,
        settings=settings,
        parallel=parallel,
        cache="fresh",
        data_dir=data_dir,
        max_tokens=default_max_tokens(model),
        cards_by_role={role: card_id},
    )
    logs = [played.log for played in report.played]
    return Arm(
        card=card_id,
        side=side,
        seeds=list(seeds),
        wins=sum(log.winner is team for log in logs),
        games=len(logs),
        clean=len(logs) == len(seeds) and all(log.stats.clean for log in logs),
        cost=sum((log.stats.cost for log in logs), Decimal("0")),
        logs=logs,
        stopped=report.stopped,
    )


def decide(champion: Arm, challenger: Arm) -> Verdict:
    """Promote the challenger only if it won at least 30 points more often on the same seeds, its
    games were all played and clean, and the champion's games were all played too. Otherwise keep
    the champion and say why."""
    if champion.seeds != challenger.seeds:
        raise ValueError("the two arms must play the same seeds")
    if challenger.stopped:
        return Verdict(False, f"the challenger's games stopped early: {challenger.stopped}")
    if challenger.games < len(challenger.seeds):
        return Verdict(
            False, f"only {challenger.games} of {len(challenger.seeds)} challenger games finished"
        )
    if champion.games < len(champion.seeds):  # fewer games than seeds is not the same test
        return Verdict(
            False, f"only {champion.games} of {len(champion.seeds)} champion games finished"
        )
    if not challenger.clean:
        return Verdict(False, "a challenger game needed a fallback answer, so it is not counted")
    gap = challenger.rate - champion.rate
    summary = f"challenger {challenger.describe()} against champion {champion.describe()}"
    if gap >= MIN_GAP:
        return Verdict(True, f"clear win: {summary}")
    if gap > 0:
        return Verdict(False, f"not clear yet: {summary}; the gap is under 30 points")
    return Verdict(False, f"no better: {summary}")
