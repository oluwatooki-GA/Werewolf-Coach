import random
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from werewolf.engine.events import Event
from werewolf.engine.roles import Role

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
    round: int = 1
