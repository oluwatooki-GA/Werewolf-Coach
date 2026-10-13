"""What one player is allowed to know. This is the only way information reaches an agent."""

from pydantic import BaseModel, ConfigDict

from werewolf.engine.events import Event
from werewolf.engine.roles import Role
from werewolf.engine.state import GameState


class PlayerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    role: Role
    round: int
    seats: tuple[str, ...]
    alive: tuple[str, ...]
    dead: tuple[str, ...]  # names only; the roles of the dead stay hidden
    partner: str | None  # set for a wolf, whose partner is known
    events: tuple[Event, ...]


def make_view(state: GameState, name: str) -> PlayerView:
    me = next(p for p in state.players if p.name == name)
    partner = next(
        (p.name for p in state.players if p.role is Role.WEREWOLF and p.name != name),
        None,
    )
    return PlayerView(
        name=name,
        role=me.role,
        round=state.round,
        seats=tuple(p.name for p in state.players),
        alive=tuple(p.name for p in state.players if p.alive),
        dead=tuple(p.name for p in state.players if not p.alive),
        partner=partner if me.role is Role.WEREWOLF else None,
        events=tuple(e for e in state.events if e.audience is None or name in e.audience),
    )
