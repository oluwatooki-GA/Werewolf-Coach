"""A cheap fact-check of what players say: does the public log back up each claim?

A model reads the public log up to a message and quotes the first statement about what a named
player said, did, voted or how they behaved that the log does not support. It sees nothing
private: no roles, no wolf chat, no notes. The count of flagged messages is a measure of
invented facts; it is not used to reject anything.
"""

import asyncio
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf.engine.events import (
    Death,
    Listening,
    NoDeath,
    NoRemoval,
    Removal,
    Speech,
    VoteCast,
)
from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import RateLimited, Request

SYSTEM = (
    "You check one message from a game of Werewolf against the public log of the game so far. "
    "Find the first statement in the message about what a named player SAID, DID, VOTED or how "
    "they BEHAVED earlier that the log does not support. Examples of unsupported statements: "
    "'you were quiet last round' when the log shows no such thing, 'last time we played', "
    "'you voted with Bo' when the log shows a different vote.\n"
    "These are fine and are not flagged: questions, opinions, guesses about motives, "
    "suggestions, predictions, statements about a death or vote that the log shows, and what "
    "the speaker says about their own role or night actions (the log cannot show those).\n"
    'Answer with JSON: {"unsupported": "<the quoted statement in under 20 words, or empty '
    'if every statement is supported>"}.'
)


class WireGround(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unsupported: str


def ground_schema() -> dict[str, Any]:
    schema = WireGround.model_json_schema()
    schema["required"] = list(schema["properties"])
    return schema


def public_log(log: GameLog, stop_before: Speech) -> str:
    """Everything every player could see, up to (not including) the given message."""
    lines_of = {id(speech): line for line, speech in numbered_speeches(log.events)}
    out: list[str] = []
    current = 0
    for event in log.events:
        if event is stop_before:
            break
        if event.audience is not None:
            continue
        if event.round != current:
            current = event.round
            out.append(f"=== Round {current} ===")
        if isinstance(event, Death):
            out.append(f"Morning: {event.player} was killed in the night.")
        elif isinstance(event, NoDeath):
            out.append("Morning: nobody died in the night.")
        elif isinstance(event, Speech):
            out.append(f"[{lines_of[id(event)]}] {event.speaker}: {event.text}")
        elif isinstance(event, Listening):
            out.append(f"{event.player} stayed quiet this turn.")
        elif isinstance(event, VoteCast):
            who = event.target or "nobody"
            out.append(f"Vote: {event.voter} voted for {who} (reason: {event.reason}).")
        elif isinstance(event, Removal):
            out.append(f"{event.player} was removed by the vote.")
        elif isinstance(event, NoRemoval):
            out.append("Nobody was removed by the vote.")
    return "\n".join(out) or "(nothing has happened yet)"


@dataclass
class GroundRun:
    checked: int = 0
    flagged: dict[str, str] = field(default_factory=dict)  # line -> the unsupported statement
    failed: dict[str, str] = field(default_factory=dict)  # line -> why it could not be checked
    cost: Decimal = Decimal("0")
    cache_hits: int = 0


class GroundStopped(Exception):
    """The spending cap or a rate limit ended the run. `run` holds what was checked before."""

    def __init__(self, message: str, run: GroundRun) -> None:
        super().__init__(message)
        self.run = run


async def check_game(
    log: GameLog, client: LLMClient, model: str, *, max_tokens: int = 200
) -> GroundRun:
    """Check every public message of a game. Raises GroundStopped on a cap or rate limit."""
    speeches = numbered_speeches(log.events)
    schema = ground_schema()
    run = GroundRun()
    stopped: list[str] = []

    async def one(line: str, speech: Speech) -> None:
        if stopped:
            return
        user = (
            f"Public log so far:\n{public_log(log, speech)}\n\n"
            f"Message to check:\n[{line}] {speech.speaker}: {speech.text}"
        )
        request = Request(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            schema=schema,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        try:
            done = await client.complete(request)
        except (LedgerBlocked, LedgerError, RateLimited) as exc:
            stopped.append(str(exc))
            return
        except Exception as exc:
            run.failed[line] = f"{type(exc).__name__}: {exc}"
            return
        run.cost += done.cost
        run.cache_hits += done.cache_hit
        if done.truncated:
            run.failed[line] = "answer cut off"
            return
        try:
            claim = WireGround.model_validate(json.loads(done.text)).unsupported.strip()
        except (ValueError, ValidationError) as exc:
            run.failed[line] = f"unreadable answer: {exc}"
            return
        run.checked += 1
        if claim and claim.lower() not in ("none", "null", "n/a"):
            run.flagged[line] = claim

    await asyncio.gather(*(one(line, speech) for line, speech in speeches))
    if stopped:
        raise GroundStopped(stopped[0], run)
    return run
