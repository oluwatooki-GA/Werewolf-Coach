"""Things that happen in a game. `audience` is who may see the event; None means everyone."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from werewolf.engine.roles import Role, Team


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    round: int
    audience: tuple[str, ...] | None = None


class WolfChat(_Event):
    kind: Literal["wolf_chat"] = "wolf_chat"
    speaker: str
    text: str


class SeerResult(_Event):
    kind: Literal["seer_result"] = "seer_result"
    target: str
    role: Role


class Death(_Event):
    kind: Literal["death"] = "death"
    player: str


class Speech(_Event):
    kind: Literal["speech"] = "speech"
    speaker: str
    text: str
    paid: int  # floor tokens spent; 0 for a free reply
    reply: bool = False


class Listening(_Event):
    kind: Literal["listening"] = "listening"
    player: str


class VoteCast(_Event):
    kind: Literal["vote_cast"] = "vote_cast"
    voter: str
    target: str | None  # None means abstained
    reason: str


class Removal(_Event):
    kind: Literal["removal"] = "removal"
    player: str


class NoRemoval(_Event):
    kind: Literal["no_removal"] = "no_removal"


class GameOver(_Event):
    kind: Literal["game_over"] = "game_over"
    winner: Team


class NoDeath(_Event):
    kind: Literal["no_death"] = "no_death"


class NightSummary(_Event):
    """What really happened overnight. Kept for analysis; audience is empty, so nobody sees it."""

    kind: Literal["night_summary"] = "night_summary"
    kill: str | None
    protect: str | None
    check: str | None
    saved: bool


Event = Annotated[
    WolfChat
    | SeerResult
    | Death
    | NoDeath
    | NightSummary
    | Speech
    | Listening
    | VoteCast
    | Removal
    | NoRemoval
    | GameOver,
    Field(discriminator="kind"),
]
