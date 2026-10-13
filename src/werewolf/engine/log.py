"""The game log: everything needed to read a game and to replay it exactly."""

import asyncio
import json
from collections import deque
from typing import Any

from pydantic import BaseModel

from werewolf.engine.actions import Task
from werewolf.engine.events import Event
from werewolf.engine.game import play_game
from werewolf.engine.roles import Role, Team
from werewolf.engine.state import CallRecord, GameState, Settings
from werewolf.engine.views import PlayerView


class PlayerRecord(BaseModel):
    name: str
    role: Role


class Stats(BaseModel):
    responses: int  # every raw answer, including rejected ones
    rejected: int  # answers the engine turned down
    failed_calls: int  # calls where both answers failed and the safe default was used
    clean: bool  # no fallback was needed


class GameLog(BaseModel):
    version: int = 1
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


def to_log(state: GameState) -> GameLog:
    if state.winner is None:
        raise ValueError("the game is not finished")
    failed = sum(c.failed for c in state.calls)
    return GameLog(
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
        ),
    )


class _Replayer:
    """Hands back one player's recorded answers in order. Needs no model."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = deque(responses)

    async def act(self, view: PlayerView, task: Task) -> object:
        if not self._responses:
            raise RuntimeError("replay ran out of recorded answers")
        return self._responses.popleft()


def replay(log: GameLog) -> GameLog:
    """Play the game again from the seed, feeding each player its recorded answers."""
    answers: dict[str, list[Any]] = {p.name: [] for p in log.players}
    for call in log.calls:
        answers[call.player].extend(call.responses)
    agents = {name: _Replayer(responses) for name, responses in answers.items()}
    return to_log(asyncio.run(play_game(log.seed, log.settings, agents)))


def replays_exactly(log: GameLog) -> bool:
    return replay(log).to_json() == log.to_json()
