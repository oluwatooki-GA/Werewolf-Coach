"""Ask several players at once, and record the calls in a fixed order."""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from werewolf.engine.actions import Action, Agent, Task
from werewolf.engine.asking import ask
from werewolf.engine.state import CallRecord, GameState
from werewolf.engine.views import make_view


@dataclass(frozen=True)
class Request:
    player: str
    task: Task
    check: Callable[[Action], str | None]


async def ask_many(
    state: GameState, agents: Mapping[str, Agent], requests: Sequence[Request]
) -> list[Action]:
    """Answers come back in request order, and calls are logged in request order too, so the
    result never depends on which agent answers first."""
    views = [make_view(state, r.player) for r in requests]
    results = await asyncio.gather(
        *(ask(agents[r.player], v, r.task, r.check) for r, v in zip(requests, views, strict=True))
    )
    for r, asked in zip(requests, results, strict=True):
        state.calls.append(
            CallRecord(
                round=state.round,
                player=r.player,
                task=r.task.model_dump(mode="json"),
                responses=asked.responses,
                errors=asked.errors,
                rejected=asked.rejected,
                failed=asked.failed,
            )
        )
    return [asked.action for asked in results]
