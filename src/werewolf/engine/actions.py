"""What the engine asks (tasks) and what an agent answers (actions). Agents may import this."""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from werewolf.engine.events import Cite
from werewolf.engine.usage import Usage as Usage
from werewolf.engine.views import PlayerView

Intent = Literal["accuse", "defend", "share_info", "ask"]


class _Task(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: str | None = None  # set on the one retry: why the last answer was rejected


class WolfChatTask(_Task):
    kind: Literal["wolf_chat"] = "wolf_chat"
    max_chars: int


class NightTargetTask(_Task):
    kind: Literal["night_target"] = "night_target"
    purpose: Literal["kill", "check", "protect"]
    options: tuple[str, ...]


class BidTask(_Task):
    kind: Literal["bid"] = "bid"
    max_bid: int
    max_chars: int
    free: bool = False  # a free turn: no bid, just post a message at no cost
    reply_to: str | None = None  # set when the free turn is a reply to this accuser


class VoteTask(_Task):
    kind: Literal["vote"] = "vote"
    options: tuple[str, ...]


class MemoryTask(_Task):
    """End of a round: write a short summary of everything that matters so far."""

    kind: Literal["memory"] = "memory"
    max_chars: int


Task = Annotated[
    WolfChatTask | NightTargetTask | BidTask | VoteTask | MemoryTask, Field(discriminator="kind")
]


class Belief(BaseModel):
    suspicion: float = Field(ge=0, le=1)
    reason: str = ""


class _Action(BaseModel):
    model_config = ConfigDict(frozen=True)

    note: str = ""  # private thought, logged but never shown to anyone
    beliefs: dict[str, Belief] = {}


class ChatAction(_Action):
    text: str


class TargetAction(_Action):
    target: str | None  # None means no target


class BidAction(_Action):
    bid: int = Field(ge=0)
    message: str = ""
    intent: Intent | None = None
    target: str | None = None
    cites: tuple[Cite, ...] = ()  # earlier lines the message points at; checked, never rejected


class VoteAction(_Action):
    target: str | None  # None means abstain
    reason: str = ""


class MemoryAction(_Action):
    summary: str


Action = ChatAction | TargetAction | BidAction | VoteAction | MemoryAction

ACTION_FOR: dict[str, type[Action]] = {
    "wolf_chat": ChatAction,
    "night_target": TargetAction,
    "bid": BidAction,
    "vote": VoteAction,
    "memory": MemoryAction,
}


class Reply(BaseModel):
    """An answer with what it cost. An agent may return this instead of a bare answer."""

    text: str
    usage: Usage | None = None


class FatalAgentError(Exception):
    """Stop the whole game, for example when the spending cap is reached. Never retried."""


class Agent(Protocol):
    async def act(self, view: PlayerView, task: Task) -> object:
        """Answer with an Action, a JSON string, or a dict. The engine checks it."""
        ...
