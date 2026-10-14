"""What one player is allowed to know. This is the only way information reaches an agent."""

from pydantic import BaseModel, ConfigDict

from werewolf.engine.events import Cite as Cite
from werewolf.engine.events import Death as Death
from werewolf.engine.events import Event as Event
from werewolf.engine.events import GameOver as GameOver
from werewolf.engine.events import Listening as Listening
from werewolf.engine.events import NoDeath as NoDeath
from werewolf.engine.events import NoRemoval as NoRemoval
from werewolf.engine.events import Removal as Removal
from werewolf.engine.events import SeerResult as SeerResult
from werewolf.engine.events import Speech as Speech
from werewolf.engine.events import VoteCast as VoteCast
from werewolf.engine.events import WolfChat as WolfChat
from werewolf.engine.record import numbered_speeches as numbered_speeches
from werewolf.engine.record import round_record as round_record
from werewolf.engine.roles import Role
from werewolf.engine.state import GameState, SpeakingMode

__all__ = [  # what a view shows, so agents never need to reach into the rest of the engine
    "Cite",
    "Death",
    "Event",
    "GameOver",
    "Listening",
    "NoDeath",
    "NoRemoval",
    "PlayerView",
    "Removal",
    "Role",
    "RuleSet",
    "SeerResult",
    "Speech",
    "VoteCast",
    "WolfChat",
    "make_view",
    "numbered_speeches",
    "round_record",
]


class RuleSet(BaseModel):
    """The public rules of this game, the same for every player."""

    model_config = ConfigDict(frozen=True)

    speaking_mode: SpeakingMode
    speaking_turns: int
    max_rounds: int
    tokens_per_day: int
    max_message_chars: int


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
    rules: RuleSet


def make_view(state: GameState, name: str) -> PlayerView:
    me = state.player(name)
    partner = next(
        (p.name for p in state.players if p.role is Role.WEREWOLF and p.name != name),
        None,
    )
    return PlayerView(
        name=name,
        role=me.role,
        round=state.round,
        seats=tuple(p.name for p in state.players),
        alive=tuple(state.alive_names()),
        dead=tuple(p.name for p in state.players if not p.alive),
        partner=partner if me.role is Role.WEREWOLF else None,
        events=tuple(e for e in state.events if e.audience is None or name in e.audience),
        rules=RuleSet(
            speaking_mode=state.settings.speaking_mode,
            speaking_turns=state.settings.speaking_turns,
            max_rounds=state.settings.max_rounds,
            tokens_per_day=state.settings.tokens_per_day,
            max_message_chars=state.settings.max_message_chars,
        ),
    )
