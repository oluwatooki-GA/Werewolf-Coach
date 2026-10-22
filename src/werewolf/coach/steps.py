"""The coach's two thinking steps: diagnose why a side lost, and write a challenger card.

Both go through the one model door (`LLMClient`) with a strict answer shape. An answer that does
not fit is asked for once more with the reason; a second miss is an error. Code, not the model,
decides the card's id (from the name the coach chose), version, role, source and parent.
"""

import json
import re
from collections.abc import Collection
from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

from werewolf.coach.evidence import SIDES, Evidence
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import RateLimited, Request
from werewolf.prompts import text
from werewolf.strategies.cards import MAX_WORDS, Card
from werewolf.tagger.moves import MOVE_NAMES

TEMPERATURE = 0.4
DIAGNOSE_TOKENS = 3000
WRITE_TOKENS = 3000
T = TypeVar("T", bound=BaseModel)


class CoachError(Exception):
    """A coach step could not finish. `cost` is what its calls cost before it gave up."""

    def __init__(self, message: str, cost: Decimal = Decimal("0")) -> None:
        super().__init__(message)
        self.cost = cost


class CoachStopped(Exception):
    """The spending cap or a rate limit ended the step. Nothing more should be asked."""


class WireDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnosis: str
    evidence: list[str]


class WireCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    instructions: str
    expected_moves: list[str]


class Diagnosis(BaseModel):
    text: str
    evidence: list[str]


def card_id(side: str, name: str, taken: Collection[str] = ()) -> str:
    """`side.name` from the idea name the coach chose: lowercase words joined by underscores,
    made unique with _2, _3 if the id is already used."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30].strip("_") or "idea"
    slug = slug.removeprefix(f"{side}_")
    chosen, number = f"{side}.{slug}", 2
    while chosen in taken:
        chosen, number = f"{side}.{slug}_{number}", number + 1
    return chosen


def _schema(wire: type[BaseModel]) -> dict[str, Any]:
    schema = wire.model_json_schema()
    schema["required"] = list(schema["properties"])
    return schema


def _describe(card: Card) -> str:
    return f"Summary: {card.summary}\nInstructions: {card.prompt_text}"


async def ask(
    client: LLMClient,
    model: str,
    system: str,
    user: str,
    wire: type[T],
    what: str,
    tokens: int,
    temperature: float = TEMPERATURE,
) -> tuple[T, Decimal]:
    """Ask once, and once more if the answer does not fit. Returns the answer and what it cost."""
    cost = Decimal("0")
    problem = ""
    for _ in range(2):
        content = user
        if problem:
            content += "\n\n" + text("coach", "invalid_answer", error=problem)
        request = Request(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            schema=_schema(wire),
            temperature=temperature,
            max_tokens=tokens,
        )
        try:
            done = await client.complete(request)
        except (LedgerBlocked, LedgerError, RateLimited) as exc:
            raise CoachStopped(str(exc)) from exc
        cost += done.cost
        if done.truncated:
            problem = "the answer was cut off"
            continue
        try:
            return wire.model_validate(json.loads(done.text)), cost
        except ValueError as exc:  # a JSON error or a pydantic ValidationError
            problem = str(exc).splitlines()[0]
    raise CoachError(f"the coach's {what} could not be read after two tries ({problem})", cost)


async def diagnose(
    client: LLMClient, model: str, evidence: Evidence, champion: Card
) -> tuple[Diagnosis, Decimal]:
    if evidence.empty:
        raise CoachError(f"nothing to diagnose: {evidence.text}")
    answer, cost = await ask(
        client,
        model,
        text("coach", "diagnose_system", rules=text("coach", "rules")),
        text(
            "coach",
            "diagnose_user",
            side=evidence.side,
            champion=_describe(champion),
            evidence=evidence.text,
        ),  # fmt: skip
        WireDiagnosis,
        "diagnosis",
        DIAGNOSE_TOKENS,
    )
    return Diagnosis(text=answer.diagnosis, evidence=answer.evidence), cost


async def write_challenger(
    client: LLMClient,
    model: str,
    side: str,
    generation: int,
    diagnosis: Diagnosis,
    champion: Card,
    feedback: list[str] | None,
    *,
    taken: Collection[str] = (),
) -> tuple[Card, Decimal]:
    """A new card for the side. `feedback` is why the last attempt was rejected; it is shown to
    the model only in this prompt, so a rejected card never carries over by itself."""
    user = text(
        "coach", "write_user",
        side=side, diagnosis=diagnosis.text, champion=_describe(champion),
        evidence_points="\n".join(f"- {point}" for point in diagnosis.evidence),
    )  # fmt: skip
    if feedback:
        reasons = "\n".join(f"- {reason}" for reason in feedback)
        user += "\n\n" + text("coach", "write_feedback", reasons=reasons)
    answer, cost = await ask(
        client,
        model,
        text(
            "coach",
            "write_system",
            max_words=MAX_WORDS,
            moves=", ".join(MOVE_NAMES),
            rules=text("coach", "rules"),
        ),
        user,
        WireCard,
        "card",
        WRITE_TOKENS,
    )
    card = Card(
        id=card_id(side, answer.name, {*taken, champion.id}),
        version=1,
        role=SIDES[side][0],
        source=f"the coach, generation {generation}, {side} side",
        summary=answer.summary.strip(),
        instructions=answer.instructions.strip(),
        expected_moves=tuple(answer.expected_moves),
        parent=champion.ref,
    )
    return card, cost
