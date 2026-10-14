import pytest

from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game


def test_player_finds_a_player_by_name() -> None:
    state = new_game(seed=1)
    assert state.player("Cy").name == "Cy"


def test_player_raises_for_an_unknown_name() -> None:
    with pytest.raises(KeyError):
        new_game(seed=1).player("Nobody")


def test_alive_names_are_in_seat_order_and_leave_out_the_dead() -> None:
    state = new_game(seed=1)
    seats = [p.name for p in state.players]
    assert state.alive_names() == seats
    state.player(seats[2]).alive = False
    assert state.alive_names() == seats[:2] + seats[3:]


def test_wolf_names_can_be_all_wolves_or_only_the_living_ones() -> None:
    state = new_game(seed=1)
    wolves = [p.name for p in state.players if p.role is Role.WEREWOLF]
    assert state.wolf_names() == wolves
    state.player(wolves[0]).alive = False
    assert state.wolf_names() == wolves
    assert state.wolf_names(alive_only=True) == wolves[1:]
