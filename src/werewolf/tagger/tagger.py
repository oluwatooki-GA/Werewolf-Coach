"""The move tagger: a model labels each public message with one or two moves.

It sees the message, the three before it and the player names. It never sees roles, private notes,
the wolf chat, bid intents or the derived labels; the game log supplies those afterwards.
"""

import asyncio
import json
from collections.abc import Collection
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf.engine.events import Speech
from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import LedgerBlocked, LedgerError
from werewolf.llm.types import RateLimited, Request
from werewolf.prompts import load
from werewolf.tagger.moves import CLAIM_MOVES, MOVE_NAMES, MOVES
from werewolf.tagger.tags import Claimed, Tag, line_key

CONTEXT_LINES = 3
ROLES = ("Seer", "Doctor", "Villager", "Werewolf")
RESULTS = ("wolf", "not_wolf")


class WireTag(BaseModel):
    """What the model fills in. Every field is required and objects are closed (strict mode)."""

    model_config = ConfigDict(extra="forbid")

    move1: str
    move2: str  # a move, or "none"
    target: str  # a player, or ""
    claim_role: str  # a role, or "none"
    checked: str  # a player, or ""
    result: str  # "wolf", "not_wolf" or "none"
    vote: str  # a player, or ""


def tag_schema() -> dict[str, Any]:
    schema = WireTag.model_json_schema()
    schema["required"] = list(schema["properties"])
    props = schema["properties"]
    props["move1"]["enum"] = list(MOVE_NAMES)
    props["move2"]["enum"] = [*MOVE_NAMES, "none"]
    props["claim_role"]["enum"] = [*ROLES, "none"]
    props["result"]["enum"] = [*RESULTS, "none"]
    return schema


def _system() -> str:
    """The instructions, from prompts/tagger.yaml; the moves come from prompts/moves.yaml."""
    spec = load("tagger")
    moves = "\n".join(f'- {n} ({fam}): {what}. Example: "{ex}"' for n, fam, what, ex in MOVES)
    rules = "\n".join(f"- {rule}" for rule in spec["rules"])
    return f"{spec['intro']}\n\nThe moves:\n{moves}\n\nRules:\n{rules}\n{spec['closing']}"


def _user(players: list[str], context: list[tuple[str, Speech]], line: str, speech: Speech) -> str:
    earlier = "\n".join(f"[{ln}] {s.speaker}: {s.text}" for ln, s in context) or "(none)"
    return (
        f"Players: {', '.join(players)}\n\nEarlier messages:\n{earlier}\n\n"
        f"Message to label:\n[{line}] {speech.speaker}: {speech.text}"
    )


def _blank(value: str) -> str:
    """Models sometimes write the word instead of leaving a field empty."""
    return "" if value.strip().lower() in ("none", "null", "n/a") else value.strip()


def to_tag(line: str, speech: Speech, wire: WireTag, players: list[str]) -> Tag | str:
    """The tag, or the reason this answer cannot be used."""
    wire = wire.model_copy(
        update={k: _blank(getattr(wire, k)) for k in ("target", "checked", "vote")}
    )
    if wire.move1 == "result_claim" or wire.move2 == "result_claim":
        if wire.claim_role not in ROLES:  # reporting a check already means "I am the Seer"
            wire = wire.model_copy(update={"claim_role": "Seer"})
    moves = [wire.move1] + ([wire.move2] if wire.move2 not in ("none", wire.move1) else [])
    unknown = [m for m in moves if m not in MOVE_NAMES]
    if unknown:
        return f"unknown move {unknown}"
    for name, value in (("target", wire.target), ("checked", wire.checked), ("vote", wire.vote)):
        if value and value not in players:
            return f"{name} '{value}' is not a player"
    claim_moves = [m for m in moves if m in CLAIM_MOVES]
    claimed: Claimed | None = None
    if claim_moves:
        if wire.claim_role not in ROLES:
            return "a claim move needs claim_role"
        if "result_claim" in moves and (
            wire.claim_role != "Seer" or not wire.checked or wire.result not in RESULTS
        ):
            return "a result_claim needs the Seer role, who was checked and the result"
        claimed = Claimed(
            role=wire.claim_role,
            checked=wire.checked if "result_claim" in moves else "",
            result=wire.result if "result_claim" in moves else "",
            vote=wire.vote,
        )
    elif wire.vote:
        claimed = Claimed(role="", vote=wire.vote)
    return Tag(
        line=line,
        speaker=speech.speaker,
        round=speech.round,
        moves=tuple(moves),
        target=wire.target or None,
        claimed=claimed,
    )


@dataclass
class TagRun:
    tags: list[Tag] = field(default_factory=list)
    untagged: dict[str, str] = field(default_factory=dict)  # line -> why
    cost: Decimal = Decimal("0")
    calls: int = 0
    cache_hits: int = 0


class TagStopped(Exception):
    """The spending cap or a rate limit ended the run. Not a bad answer: stop and report.
    `run` holds what was tagged before the stop."""

    def __init__(self, message: str, run: TagRun) -> None:
        super().__init__(message)
        self.run = run


async def tag_game(
    log: GameLog,
    client: LLMClient,
    model: str,
    *,
    max_tokens: int = 300,
    only: Collection[str] | None = None,
) -> TagRun:
    """Tag every public message of a game (or just the lines in `only`). Raises TagStopped."""
    speeches = numbered_speeches(log.events)
    players = [p.name for p in log.players]
    system, schema = _system(), tag_schema()
    run = TagRun()
    stopped: list[str] = []

    async def one(index: int) -> None:
        line, speech = speeches[index]
        if stopped:
            return
        request = Request(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _user(
                    players, speeches[max(0, index - CONTEXT_LINES):index], line, speech
                )},
            ],
            schema=schema,
            temperature=0.0,
            max_tokens=max_tokens,
        )  # fmt: skip
        try:
            done = await client.complete(request)
        except (LedgerBlocked, LedgerError, RateLimited) as exc:
            stopped.append(str(exc))
            return
        except Exception as exc:
            run.untagged[line] = f"{type(exc).__name__}: {exc}"
            return
        run.calls += 1
        run.cache_hits += done.cache_hit
        run.cost += done.cost
        if done.truncated:
            run.untagged[line] = "answer cut off"
            return
        try:
            result = to_tag(line, speech, WireTag.model_validate(json.loads(done.text)), players)
        except (ValueError, ValidationError) as exc:
            run.untagged[line] = f"unreadable answer: {exc}"
            return
        if isinstance(result, str):
            run.untagged[line] = result
        else:
            run.tags.append(result)

    wanted = [i for i, (line, _) in enumerate(speeches) if only is None or line in only]
    await asyncio.gather(*(one(i) for i in wanted))
    run.tags.sort(key=lambda t: line_key(t.line))
    if stopped:
        raise TagStopped(stopped[0], run)
    return run
