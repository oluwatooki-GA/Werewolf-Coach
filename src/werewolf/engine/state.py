import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from werewolf.engine.events import Event
from werewolf.engine.roles import Role, Team
from werewolf.engine.usage import Usage

DEFAULT_NAMES = ("Ada", "Bo", "Cy", "Di", "Eve", "Fay", "Gus", "Hal")


class SpeakingMode(StrEnum):
    FIXED_ORDER = "fixed_order"
    FREE_BID = "free_bid"
    FLOOR_TOKENS = "floor_tokens"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaking_mode: SpeakingMode = SpeakingMode.FLOOR_TOKENS
    speaking_turns: int = 8
    max_rounds: int = 6
    tokens_per_day: int = 3
    max_message_chars: int = 300
    names: tuple[str, ...] = DEFAULT_NAMES
    cards: dict[str, str] = {}  # seat name -> strategy card id; logged, never shown to the engine

    @field_validator("names")
    @classmethod
    def _eight_unique_names(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if len(names) != 8 or len(set(names)) != 8:
            raise ValueError("exactly 8 unique names are needed")
        return names


class CallRecord(BaseModel):
    """One ask of one agent: the task, every raw answer, and how it went."""

    round: int
    player: str
    task: dict[str, Any]
    responses: list[Any]
    errors: list[str]
    rejected: int
    failed: bool
    usage: list[Usage | None] = []  # one per response; empty in logs from before usage existed


@dataclass
class Player:
    name: str
    role: Role
    alive: bool = True


@dataclass
class GameState:
    """The true state. Only the engine holds this; agents get a PlayerView."""

    seed: int
    settings: Settings
    players: list[Player]
    rng: random.Random
    events: list[Event] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)
    round: int = 1
    winner: Team | None = None
