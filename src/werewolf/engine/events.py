"""Things that happen in a game. `audience` is who may see the event; None means everyone."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from werewolf.engine.roles import Role


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


Event = Annotated[WolfChat | SeerResult | Death, Field(discriminator="kind")]
