"""Things that happen in a game. `audience` is who may see the event; None means everyone."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

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


class Cite(BaseModel):
    """A message points at an earlier line: its number, and who the message says wrote it."""

    model_config = ConfigDict(frozen=True)

    line: str  # such as "R2-4": round 2, public message 4
    speaker: str


class Speech(_Event):
    kind: Literal["speech"] = "speech"
    speaker: str
    text: str
    paid: int  # floor tokens spent; 0 for a free reply
    reply: bool = False
    cites: tuple[Cite, ...] = ()
    invented: tuple[str, ...] = ()  # the cited lines that are not real: missing, or by someone else

    @model_serializer(mode="wrap")
    def _leave_out_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ("cites", "invented"):  # so a log without cites keeps its exact old bytes
            if not data.get(key):
                data.pop(key, None)
        return data


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
