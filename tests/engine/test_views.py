import pytest
from pydantic import ValidationError

from werewolf.engine.events import Death, WolfChat
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState
from werewolf.engine.views import PlayerView, make_view


def by_role(state: GameState, role: Role) -> list[str]:
    return [p.name for p in state.players if p.role is role]


def test_a_view_shows_the_players_own_name_and_role() -> None:
    state = new_game(seed=1)
    seer = by_role(state, Role.SEER)[0]
    view = make_view(state, seer)
    assert (view.name, view.role) == (seer, Role.SEER)


def test_a_wolf_sees_its_partner() -> None:
    state = new_game(seed=1)
    first, second = by_role(state, Role.WEREWOLF)
    assert make_view(state, first).partner == second
    assert make_view(state, second).partner == first


def test_nobody_else_sees_a_partner() -> None:
    state = new_game(seed=1)
    for p in state.players:
        if p.role is not Role.WEREWOLF:
            assert make_view(state, p.name).partner is None


def test_the_dead_are_listed_by_name_only() -> None:
    state = new_game(seed=1)
    victim = by_role(state, Role.VILLAGER)[0]
    next(p for p in state.players if p.name == victim).alive = False
    view = make_view(state, by_role(state, Role.SEER)[0])
    assert view.dead == (victim,)
    assert victim not in view.alive
    assert len(view.alive) == 7


def test_a_view_only_holds_events_meant_for_that_player() -> None:
    state = new_game(seed=1)
    wolf, partner = by_role(state, Role.WEREWOLF)
    villager = by_role(state, Role.VILLAGER)[0]
    state.events.append(Death(round=1, player=villager))
    state.events.append(WolfChat(round=1, speaker=wolf, text="hi", audience=(wolf, partner)))
    assert [e.kind for e in make_view(state, wolf).events] == ["death", "wolf_chat"]
    assert [e.kind for e in make_view(state, villager).events] == ["death"]


def test_a_view_cannot_be_changed() -> None:
    state = new_game(seed=1)
    view = make_view(state, state.players[0].name)
    with pytest.raises(ValidationError):
        view.name = "Mallory"


def test_the_view_fields_are_the_whole_public_surface() -> None:
    assert set(PlayerView.model_fields) == {
        "name", "role", "round", "seats", "alive", "dead", "partner", "events", "rules",
    }  # fmt: skip


def test_the_view_carries_the_public_rules_of_the_game() -> None:
    from werewolf.engine.state import Settings, SpeakingMode

    state = new_game(
        seed=1, settings=Settings(speaking_mode=SpeakingMode.FREE_BID, speaking_turns=5)
    )
    rules = make_view(state, state.players[0].name).rules
    assert rules.speaking_mode == SpeakingMode.FREE_BID
    assert (rules.speaking_turns, rules.max_rounds, rules.tokens_per_day) == (5, 6, 3)
    assert rules.max_message_chars == 300
    assert all(make_view(state, p.name).rules == rules for p in state.players)
