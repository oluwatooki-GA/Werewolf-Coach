from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState
from werewolf.engine.win import winner


def with_alive(wolves: int, others: int, round_: int = 1) -> GameState:
    """A game where exactly this many wolves and non-wolves are alive."""
    state = new_game(seed=1)
    state.round = round_
    kept = {Role.WEREWOLF: wolves, "other": others}
    for p in state.players:
        key = Role.WEREWOLF if p.role is Role.WEREWOLF else "other"
        p.alive = kept[key] > 0
        kept[key] -= 1
    return state


def test_the_village_wins_when_both_wolves_are_gone() -> None:
    assert winner(with_alive(0, 6), round_complete=False) is Team.VILLAGE


def test_the_wolves_win_when_they_equal_the_rest() -> None:
    assert winner(with_alive(2, 2), round_complete=False) is Team.WOLVES
    assert winner(with_alive(1, 1), round_complete=False) is Team.WOLVES


def test_the_wolves_win_when_they_outnumber_the_rest() -> None:
    assert winner(with_alive(2, 1), round_complete=False) is Team.WOLVES
    assert winner(with_alive(1, 0), round_complete=False) is Team.WOLVES


def test_no_winner_while_the_village_still_outnumbers_the_wolves() -> None:
    assert winner(with_alive(2, 6), round_complete=False) is None
    assert winner(with_alive(2, 3), round_complete=True) is None
    assert winner(with_alive(1, 2), round_complete=False) is None


def test_after_the_sixth_round_with_no_winner_the_village_wins() -> None:
    assert winner(with_alive(2, 4, round_=6), round_complete=True) is Team.VILLAGE


def test_the_round_limit_waits_until_the_round_is_over() -> None:
    assert winner(with_alive(2, 4, round_=6), round_complete=False) is None


def test_before_the_sixth_round_ends_there_is_no_limit_win() -> None:
    assert winner(with_alive(2, 4, round_=5), round_complete=True) is None


def test_the_wolves_can_still_win_in_the_last_round() -> None:
    assert winner(with_alive(2, 2, round_=6), round_complete=True) is Team.WOLVES
