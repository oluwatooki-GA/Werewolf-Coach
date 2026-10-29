import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

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
    speaking_turns: int = 10
    max_rounds: int = 6
    tokens_per_day: int = 4
    max_message_chars: int = 300
    summarize_rounds: bool = False  # ask every player for a summary at the end of each round
    max_summary_chars: int = 800
    # 0 is the old night: each wolf writes one message at the same time. Above 0 the wolves talk in
    # turn, up to this many messages a night, and either can end the chat by sending nothing.
    wolf_chat_messages: int = 0
    names: tuple[str, ...] = DEFAULT_NAMES
    cards: dict[str, str] = {}  # seat name -> strategy card id; logged, never shown to the engine
    personas: dict[str, str] = {}  # seat name -> table manner id; logged, the engine ignores it

    @field_validator("names")
    @classmethod
    def _eight_unique_names(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if len(names) != 8 or len(set(names)) != 8:
            raise ValueError("exactly 8 unique names are needed")
        return names

    @model_serializer(mode="wrap")
    def _leave_out_defaults_old_logs_lack(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not data.get("personas"):  # so a log without personas keeps its exact old bytes
            data.pop("personas", None)
        if not data.get("wolf_chat_messages"):  # and so does a log from before the wolf chat grew
            data.pop("wolf_chat_messages", None)
        return data


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

    def player(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    def alive_names(self) -> list[str]:
        """Living players, in seat order."""
        return [p.name for p in self.players if p.alive]

    def wolf_names(self, alive_only: bool = False) -> list[str]:
        return [
            p.name for p in self.players if p.role is Role.WEREWOLF and (p.alive or not alive_only)
        ]
