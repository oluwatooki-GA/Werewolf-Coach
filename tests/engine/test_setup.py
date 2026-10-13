import random
from collections import Counter

import pytest
from pydantic import ValidationError

from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings, SpeakingMode


def test_eight_players_with_two_wolves_a_seer_a_doctor_and_four_villagers() -> None:
    state = new_game(seed=1)
    assert len(state.players) == 8
    assert Counter(p.role for p in state.players) == {
        Role.WEREWOLF: 2,
        Role.SEER: 1,
        Role.DOCTOR: 1,
        Role.VILLAGER: 4,
    }


def test_everyone_starts_alive_with_a_unique_name() -> None:
    state = new_game(seed=1)
    assert all(p.alive for p in state.players)
    assert len({p.name for p in state.players}) == 8


def test_the_same_seed_gives_the_same_seats_and_roles() -> None:
    first = [(p.name, p.role) for p in new_game(seed=42).players]
    second = [(p.name, p.role) for p in new_game(seed=42).players]
    assert first == second


def test_different_seeds_give_different_games() -> None:
    games = {tuple((p.name, p.role) for p in new_game(seed=s).players) for s in range(10)}
    assert len(games) > 1


def test_setup_uses_only_its_own_seeded_random(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("global random used")

    for name in ("random", "shuffle", "choice", "randint", "sample", "seed"):
        monkeypatch.setattr(random, name, forbidden)
    new_game(seed=3)


def test_default_settings_follow_the_design() -> None:
    s = Settings()
    assert s.speaking_mode is SpeakingMode.FLOOR_TOKENS
    assert (s.speaking_turns, s.max_rounds, s.tokens_per_day, s.max_message_chars) == (8, 6, 3, 300)
    assert s.cards == {}


def test_settings_need_exactly_eight_unique_names() -> None:
    with pytest.raises(ValidationError):
        Settings(names=("Ada", "Bo"))
    with pytest.raises(ValidationError):
        Settings(names=("Ada",) * 8)


def test_a_card_id_per_seat_is_kept_in_the_settings_for_the_log() -> None:
    state = new_game(seed=1, settings=Settings(cards={"Ada": "wolf.lie_low"}))
    assert state.settings.cards == {"Ada": "wolf.lie_low"}
