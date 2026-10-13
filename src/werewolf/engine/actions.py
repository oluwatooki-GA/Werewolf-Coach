"""What the engine asks (tasks) and what an agent answers (actions). Agents may import this."""
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

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


class VoteTask(_Task):
    kind: Literal["vote"] = "vote"
    options: tuple[str, ...]


Task = Annotated[WolfChatTask | NightTargetTask | BidTask | VoteTask, Field(discriminator="kind")]


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


class VoteAction(_Action):
    target: str | None  # None means abstain
    reason: str = ""


Action = ChatAction | TargetAction | BidAction | VoteAction

ACTION_FOR: dict[str, type[Action]] = {
    "wolf_chat": ChatAction,
    "night_target": TargetAction,
    "bid": BidAction,
    "vote": VoteAction,
}


class Agent(Protocol):
    async def act(self, view: PlayerView, task: Task) -> object:
        """Answer with an Action, a JSON string, or a dict. The engine checks it."""
        ...
