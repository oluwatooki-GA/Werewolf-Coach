"""Hidden information: no PlayerView holds another player's role, the wolf chat (unless the
viewer is a wolf), or Seer results (unless the viewer is the Seer)."""
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from werewolf.engine.events import Death, SeerResult, WolfChat
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Player
from werewolf.engine.views import make_view

WOLF_CODE = "CODEWORD-WOLFCHAT-7731"
SEEDS = range(6)


def planted_state(seed: int) -> GameState:
    state = new_game(seed)
    wolves = tuple(p.name for p in state.players if p.role is Role.WEREWOLF)
    seer = next(p for p in state.players if p.role is Role.SEER)
    doctor = next(p for p in state.players if p.role is Role.DOCTOR)
    villager = next(p for p in state.players if p.role is Role.VILLAGER)
    state.events.append(WolfChat(round=1, speaker=wolves[0], text=WOLF_CODE, audience=wolves))
    state.events.append(
        SeerResult(round=1, target=doctor.name, role=doctor.role, audience=(seer.name,))
    )
    state.events.append(Death(round=1, player=villager.name))
    return state


def strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from strings(item)


def dicts(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from dicts(item)


def mentions(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def revealed_roles(viewer: Player, others: list[Player], view_json: str) -> list[str]:
    """Other players whose name and role appear together in the view."""
    tree = json.loads(view_json)
    found = []
    for other in others:
        allowed_partner = viewer.role is Role.WEREWOLF and other.role is Role.WEREWOLF
        for d in dicts(tree):
            values = [v for v in d.values() if isinstance(v, str)]
            if other.name in values and other.role.value in values:
                seer_result = d.get("kind") == "seer_result" and viewer.role is Role.SEER
                if not (allowed_partner or seer_result):
                    found.append(other.name)
        for text in strings(tree):
            if mentions(text, other.name) and mentions(text, other.role.value):
                found.append(other.name)
    return found


@pytest.mark.parametrize("seed", SEEDS)
def test_the_wolf_chat_reaches_only_the_wolves(seed: int) -> None:
    state = planted_state(seed)
    for p in state.players:
        text = make_view(state, p.name).model_dump_json()
        assert (WOLF_CODE in text) == (p.role is Role.WEREWOLF), p.name


@pytest.mark.parametrize("seed", SEEDS)
def test_seer_results_reach_only_the_seer(seed: int) -> None:
    state = planted_state(seed)
    for p in state.players:
        text = make_view(state, p.name).model_dump_json()
        assert ("seer_result" in text) == (p.role is Role.SEER), p.name


@pytest.mark.parametrize("seed", SEEDS)
def test_no_view_holds_another_players_role(seed: int) -> None:
    state = planted_state(seed)
    for p in state.players:
        others = [q for q in state.players if q.name != p.name]
        text = make_view(state, p.name).model_dump_json()
        assert revealed_roles(p, others, text) == [], p.name


def test_the_role_check_catches_a_planted_role_leak() -> None:
    state = planted_state(1)
    villager = next(p for p in state.players if p.role is Role.VILLAGER)
    wolf = next(p for p in state.players if p.role is Role.WEREWOLF)
    others = [q for q in state.players if q.name != villager.name]
    leaked = f'{{"note": "{wolf.name} is secretly a {wolf.role.value}"}}'
    assert revealed_roles(villager, others, leaked) == [wolf.name]
