"""Ask an agent for an action: check it, retry once with the reason, then fall back."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from werewolf.engine.actions import (
    ACTION_FOR,
    Action,
    Agent,
    BidAction,
    ChatAction,
    FatalAgentError,
    MemoryAction,
    Reply,
    TargetAction,
    Task,
    VoteAction,
)
from werewolf.engine.usage import Usage
from werewolf.engine.views import PlayerView

EXCEPTION_KEY = "__exception__"  # how a raised error is stored in the log, so replay can repeat it


@dataclass
class Asked:
    action: Action
    responses: list[Any]  # every raw answer in order, as JSON-able data
    errors: list[str] = field(default_factory=list)
    attempts: int = 1
    rejected: int = 0
    failed: bool = False  # True when both answers were rejected and the default was used
    usage: list[Usage | None] = field(default_factory=list)  # one per response, None if unknown


def default_action(task: Task) -> Action:
    match task.kind:
        case "wolf_chat":
            return ChatAction(text="")
        case "night_target":
            return TargetAction(target=None)
        case "bid":
            return BidAction(bid=0)
        case "vote":
            return VoteAction(target=None, reason="")
        case "memory":
            return MemoryAction(summary="")


def _record(raw: object) -> Any:
    if isinstance(raw, (ChatAction, TargetAction, BidAction, VoteAction, MemoryAction)):
        return raw.model_dump(mode="json")
    if isinstance(raw, (str, dict)):
        return raw
    return {EXCEPTION_KEY: f"unreadable answer of type {type(raw).__name__}"}


def _coerce(raw: object, task: Task) -> tuple[Action | None, str | None]:
    expected = ACTION_FOR[task.kind]
    if isinstance(raw, dict) and EXCEPTION_KEY in raw:
        return None, f"agent error: {raw[EXCEPTION_KEY]}"
    if isinstance(raw, expected):
        return raw, None
    try:
        if isinstance(raw, str):
            return expected.model_validate_json(raw), None
        if isinstance(raw, dict):
            return expected.model_validate(raw), None
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "answer"
        return None, f"{where}: {first['msg']}"
    return None, f"expected a {task.kind} action"


async def ask(
    agent: Agent,
    view: PlayerView,
    task: Task,
    check: Callable[[Action], str | None],
) -> Asked:
    responses: list[Any] = []
    usages: list[Usage | None] = []
    errors: list[str] = []
    current = task
    for attempt in (1, 2):
        used: Usage | None = None
        try:
            raw = await agent.act(view, current)
        except FatalAgentError:
            raise  # for example the spending cap: stop the game, do not paper over it
        except Exception as exc:  # a broken agent must never crash the game
            raw = {EXCEPTION_KEY: f"{type(exc).__name__}: {exc}"}
        if isinstance(raw, Reply):
            used, raw = raw.usage, raw.text
        responses.append(_record(raw))
        usages.append(used)
        action, error = _coerce(raw, task)
        if action is not None:
            error = check(action)
            if error is None:
                return Asked(action, responses, errors, attempt, attempt - 1, False, usages)
        errors.append(error or "rejected")
        current = task.model_copy(update={"error": error})
    return Asked(default_action(task), responses, errors, 2, 2, True, usages)
