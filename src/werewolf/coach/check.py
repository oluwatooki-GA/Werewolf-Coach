"""Check a challenger card before any game uses it, and rewrite it when it fails.

Two checks, cheapest first. Code checks (the card rules, no player names, valid moves, not a copy
of the champion) run before any model is asked. Then a small model reads only the role and the
card text, never the games, and says whether the card leans on something that role cannot know or
breaks a rule. A card that fails is written again with the reasons, twice at most; a card that
never passes is not returned.
"""

import math
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from werewolf.coach.steps import CoachError, Diagnosis, ask, write_challenger
from werewolf.llm.client import LLMClient
from werewolf.prompts import text
from werewolf.strategies.cards import Card, check_card

MIN_KEPT = 0.5  # the share of the champion's sentences a new card must keep
MAX_ATTEMPTS = 3  # the first card and two rewrites
CHECK_TOKENS = 1000


class WireCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    reasons: list[str]


@dataclass
class CheckOutcome:
    card: Card | None  # the card that passed, or None if no attempt passed
    attempts: int
    reasons: list[list[str]] = field(default_factory=list)  # one list per failed attempt
    cost: Decimal = Decimal("0")

    @property
    def validity(self) -> float:
        """The share of attempts that passed (DESIGN 7.1): 1 for a first try, 0 for none."""
        return (1 if self.card else 0) / self.attempts if self.attempts else 0


def sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if part]


def changes(base: Card, card: Card) -> list[str]:
    """What the card took out of its base and what it put in, one sentence per line."""
    old, new = sentences(base.prompt_text), sentences(card.prompt_text)
    return [f"- {s}" for s in old if s not in new] + [f"+ {s}" for s in new if s not in old]


def code_problems(card: Card, champion: Card) -> list[str]:
    problems = check_card(card)
    if card.prompt_text == champion.prompt_text:
        problems.append("the card has the same instructions as the champion; change something")
    else:
        base = sentences(champion.prompt_text)
        kept = [s for s in base if s in sentences(card.prompt_text)]
        need = math.ceil(len(base) * MIN_KEPT)
        if len(kept) < need:
            problems.append(
                f"the card keeps {len(kept)} of the champion's {len(base)} sentences; keep at "
                f"least {need} word for word and change only what the diagnosis contradicts"
            )
    return problems


async def model_problems(client: LLMClient, model: str, card: Card) -> tuple[list[str], Decimal]:
    """What a small model finds wrong with the card, seeing only its role and its text."""
    answer, cost = await ask(
        client,
        model,
        text("coach", "check_system", rules=text("coach", "rules")),
        text(
            "coach",
            "check_user",
            role=card.role.value,
            card=f"{card.summary}\n{card.prompt_text}",
        ),  # fmt: skip
        WireCheck,
        "card check",
        CHECK_TOKENS,
        temperature=0.0,
    )
    if answer.ok:
        return [], cost
    return answer.reasons or ["the check model rejected the card without a reason"], cost


async def write_checked_card(
    client: LLMClient,
    write_model: str,
    check_model: str,
    side: str,
    generation: int,
    diagnosis: Diagnosis,
    champion: Card,
    *,
    taken: Collection[str] = (),
) -> CheckOutcome:
    """Write a card and check it; rewrite with the reasons until one passes or tries run out."""
    outcome = CheckOutcome(card=None, attempts=0)
    feedback: list[str] | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            card, cost = await write_challenger(
                client, write_model, side, generation, diagnosis, champion, feedback, taken=taken
            )
            outcome.cost += cost
            outcome.attempts += 1
            problems = code_problems(card, champion)
            if not problems:
                problems, cost = await model_problems(client, check_model, card)
                outcome.cost += cost
        except CoachError as exc:  # keep what the calls so far cost
            raise CoachError(str(exc), outcome.cost + exc.cost) from exc
        if not problems:
            outcome.card = card
            return outcome
        outcome.reasons.append(problems)
        feedback = problems
    return outcome
