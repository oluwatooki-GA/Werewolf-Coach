"""The record of every coach generation: what it read, thought, wrote, tested and decided.

One JSON file per generation under `data/coach/<side>/`. A file is written to a temporary name
and renamed, so a crash never leaves a half-written generation that looks finished. The record is
also what the README's family tree is made from.
"""

import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ValidationError

COACH_DIR = Path("data/coach")


class ArmResult(BaseModel):
    card: str  # id@version
    seeds: list[int]
    wins: int
    games: int
    clean: bool
    cost: Decimal
    stopped: str | None = None


class CheckSummary(BaseModel):
    attempts: int  # how many times a card was written before one passed (or the tries ran out)
    passed: bool
    reasons: list[list[str]] = []  # the reasons each failed attempt gave


class Generation(BaseModel):
    side: str
    number: int
    champion_before: str
    champion_after: str
    evidence: str  # a one-line description of what the coach read
    diagnosis: str
    challenger_card: str | None  # id@version, or None if no card ever passed its checks
    challenger_text: str
    check: CheckSummary
    champion_arm: ArmResult | None
    challenger_arm: ArmResult | None
    promote: bool
    decision: str
    coach_cost: Decimal = Decimal("0")

    @property
    def player_cost(self) -> Decimal:
        arms = (self.champion_arm, self.challenger_arm)
        return sum((a.cost for a in arms if a is not None), Decimal("0"))

    @property
    def cost(self) -> Decimal:
        return self.coach_cost + self.player_cost


def _path(side: str, number: int, root: Path) -> Path:
    return root / side / f"gen-{number:03d}.json"


def save_generation(gen: Generation, root: Path = COACH_DIR) -> Path:
    """Save a finished generation. A saved generation is never replaced."""
    path = _path(gen.side, gen.number, root)
    if path.exists():
        raise ValueError(f"generation {gen.number} of the {gen.side} side is already saved")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(gen.model_dump_json(indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def load_history(side: str, root: Path = COACH_DIR) -> list[Generation]:
    """The finished generations, in order. It stops at the first file that is missing or unreadable,
    so a half-written file and anything after it do not count."""
    found: list[Generation] = []
    number = 1
    while _path(side, number, root).exists():
        try:
            found.append(
                Generation.model_validate_json(_path(side, number, root).read_text("utf-8"))
            )
        except (OSError, ValidationError):
            break
        number += 1
    return found


def last_complete(side: str, root: Path = COACH_DIR) -> int:
    """The number of the last finished generation (0 if none): a crashed run resumes after it."""
    return len(load_history(side, root))


def total_cost(side: str, root: Path = COACH_DIR) -> Decimal:
    return sum((g.cost for g in load_history(side, root)), Decimal("0"))


def _first_line(text: str, limit: int = 110) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _arm(arm: ArmResult | None) -> str:
    return f"{arm.wins}/{arm.games}" if arm else "not played"


def family_tree(side: str, root: Path = COACH_DIR) -> str:
    """A readable account of the line of champions: card, diagnosis, results, verdict."""
    history = load_history(side, root)
    if not history:
        return f"{side} side: no generations yet."
    lines = [f"{side} side. Started from {history[0].champion_before}."]
    for gen in history:
        if gen.challenger_card is None:
            lines.append(
                f"Generation {gen.number}: {gen.decision}. The coach wrote {gen.check.attempts} "
                "cards and none passed its checks, so none was played (never played)."
            )
        else:
            verdict = "kept as the new champion" if gen.promote else "dropped"
            lines.append(
                f"Generation {gen.number}: {gen.challenger_card} {verdict} "
                f"(champion {_arm(gen.champion_arm)} against challenger "
                f"{_arm(gen.challenger_arm)}). {gen.decision}."
            )
        lines.append(f"  diagnosis: {_first_line(gen.diagnosis)}")
        if gen.challenger_text:
            lines.append(f"  card: {_first_line(gen.challenger_text, 160)}")
    lines.append(
        f"Champion now: {history[-1].champion_after}. Cost so far: ${total_cost(side, root):.4f}."
    )
    return "\n".join(lines)
