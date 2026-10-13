"""The game log: everything needed to read a game and to replay it exactly."""

import asyncio
import json
from collections import deque
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from werewolf.engine.actions import Reply, Task
from werewolf.engine.events import Event
from werewolf.engine.game import play_game
from werewolf.engine.roles import Role, Team
from werewolf.engine.state import CallRecord, GameState, Settings
from werewolf.engine.usage import Usage
from werewolf.engine.views import PlayerView


class PlayerRecord(BaseModel):
    name: str
    role: Role


class Stats(BaseModel):
    responses: int  # every raw answer, including rejected ones
    rejected: int  # answers the engine turned down
    failed_calls: int  # calls where both answers failed and the safe default was used
    clean: bool  # no fallback was needed
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost: Decimal = Decimal("0")  # dollars, exact
    truncated: int = 0  # answers cut off by the output limit


class GameLog(BaseModel):
    version: int = 2
    run_id: str = ""  # unique per run; also the response-cache salt in experiment runs
    seed: int
    settings: Settings
    players: list[PlayerRecord]
    events: list[Event]
    calls: list[CallRecord]
    winner: Team
    rounds: int
    stats: Stats

    def to_json(self) -> str:
        """Canonical text: sorted keys, no spaces, plain ASCII, one trailing newline."""
        data: dict[str, Any] = self.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "GameLog":
        return cls.model_validate_json(text)


def to_log(state: GameState, run_id: str = "") -> GameLog:
    if state.winner is None:
        raise ValueError("the game is not finished")
    failed = sum(c.failed for c in state.calls)
    used = [u for c in state.calls for u in c.usage if u is not None]
    return GameLog(
        run_id=run_id,
        seed=state.seed,
        settings=state.settings,
        players=[PlayerRecord(name=p.name, role=p.role) for p in state.players],
        events=list(state.events),
        calls=list(state.calls),
        winner=state.winner,
        rounds=state.round,
        stats=Stats(
            responses=sum(len(c.responses) for c in state.calls),
            rejected=sum(c.rejected for c in state.calls),
            failed_calls=failed,
            clean=failed == 0,
            prompt_tokens=sum(u.prompt_tokens for u in used),
            completion_tokens=sum(u.completion_tokens for u in used),
            cached_tokens=sum(u.cached_tokens for u in used),
            cost=sum((u.cost for u in used), Decimal("0")),
            truncated=sum(u.truncated for u in used),
        ),
    )


class _Replayer:
    """Hands back one player's recorded answers in order, with their usage. Needs no model."""

    def __init__(self, answers: list[tuple[Any, Usage | None]]) -> None:
        self._answers = deque(answers)

    async def act(self, view: PlayerView, task: Task) -> object:
        if not self._answers:
            raise RuntimeError("replay ran out of recorded answers")
        response, usage = self._answers.popleft()
        if usage is not None and isinstance(response, str):
            return Reply(text=response, usage=usage)
        return response


def replay(log: GameLog) -> GameLog:
    """Play the game again from the seed, feeding each player its recorded answers."""
    answers: dict[str, list[tuple[Any, Usage | None]]] = {p.name: [] for p in log.players}
    for call in log.calls:
        usage = call.usage or [None] * len(call.responses)  # logs from before usage existed
        answers[call.player].extend(zip(call.responses, usage, strict=True))
    agents = {name: _Replayer(recorded) for name, recorded in answers.items()}
    state = asyncio.run(play_game(log.seed, log.settings, agents))
    return to_log(state, run_id=log.run_id)


def replays_exactly(log: GameLog) -> bool:
    return replay(log).to_json() == log.to_json()
