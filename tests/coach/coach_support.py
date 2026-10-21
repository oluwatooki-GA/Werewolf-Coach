"""Small hand-made games for the coach tests: roles known, events chosen, winner chosen."""

import asyncio
import json
from collections.abc import Sequence
from typing import cast

from werewolf.agents.scripted import policy
from werewolf.engine.events import Event, Removal, Speech, VoteCast
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.state import CallRecord
from werewolf.tagger.tags import Claimed, Tag, TagFile

Game = tuple[GameLog, TagFile | None]


def who(role: Role, index: int = 0) -> str:
    """The name of the index-th player with this role on seed 1."""
    return [p.name for p in new_game(1).players if p.role is role][index]


WOLF_A, WOLF_B = who(Role.WEREWOLF, 0), who(Role.WEREWOLF, 1)
SEER, DOCTOR = who(Role.SEER), who(Role.DOCTOR)
VILLAGERS = [who(Role.VILLAGER, i) for i in range(4)]


def speech(round_: int, speaker: str, text: str) -> Speech:
    return Speech(round=round_, speaker=speaker, text=text, paid=1)


def vote(round_: int, voter: str, target: str, reason: str = "r") -> VoteCast:
    return VoteCast(round=round_, voter=voter, target=target, reason=reason)


def note_call(round_: int, player: str, note: str, kind: str = "vote") -> CallRecord:
    answer = json.dumps({"target": None, "reason": "", "note": note, "beliefs": {}})
    task = {"kind": kind, "options": []}
    return CallRecord(
        round=round_, player=player, task=task, responses=[answer], errors=[], rejected=0,
        failed=False,
    )  # fmt: skip


def make_log(
    winner: Team,
    events: Sequence[object],
    *,
    rounds: int = 2,
    card: str | None = None,
    side_role: Role = Role.WEREWOLF,
    calls: list[CallRecord] | None = None,
) -> GameLog:
    """A real, valid log (from a scripted game on seed 1) with our events, winner and cards."""
    players = new_game(1).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    base = to_log(asyncio.run(play_game(1, None, {p.name: policy(wolves) for p in players})))
    cards = {p.name: card for p in players if p.role is side_role} if card else {}
    settings = base.settings.model_copy(update={"cards": cards})
    return base.model_copy(
        update={
            "events": cast(list[Event], list(events)),
            "winner": winner, "rounds": rounds, "settings": settings, "calls": calls or [],
        }
    )  # fmt: skip


def tags_for(*tags: Tag) -> TagFile:
    return TagFile(model="m", tags=list(tags))


def tag(line: str, speaker: str, round_: int, *moves: str, target: str | None = None) -> Tag:
    return Tag(line=line, speaker=speaker, round=round_, moves=moves, target=target)


def claim_tag(line: str, speaker: str, role: str) -> Tag:
    return Tag(
        line=line, speaker=speaker, round=1, moves=("role_claim",), claimed=Claimed(role=role)
    )


def removed(round_: int, player: str) -> Removal:
    return Removal(round=round_, player=player)
