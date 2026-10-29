"""The play caps: how much may be spent today and in all, and who may start a game."""

from decimal import Decimal

import pytest
from sqlalchemy import Engine

from werewolf.play.budget import Caps, check
from werewolf.store import make_engine
from werewolf.store.play import add_spend, spent_today, spent_total

CAPS = Caps(daily=Decimal("1.00"), total=Decimal("10.00"), estimate=Decimal("0.30"))
DAY, NEXT = "2026-10-29", "2026-10-30"


@pytest.fixture
def engine() -> Engine:
    return make_engine("sqlite:///:memory:")


def verdict(engine: Engine, running: int = 0, day: str = DAY) -> tuple[str, str]:
    with engine.connect() as conn:
        result = check(conn, CAPS, running=running, day=day)
    return result.state, result.reason


def test_a_fresh_day_with_nothing_spent_is_open(engine: Engine) -> None:
    assert verdict(engine) == ("open", "")


def test_spending_adds_up_by_day_and_in_all(engine: Engine) -> None:
    with engine.begin() as conn:
        add_spend(conn, DAY, 0.25)
        add_spend(conn, DAY, 0.25)
        add_spend(conn, NEXT, 0.10)
    with engine.connect() as conn:
        assert round(spent_today(conn, DAY), 2) == 0.50
        assert round(spent_today(conn, NEXT), 2) == 0.10
        assert round(spent_total(conn), 2) == 0.60


def test_when_the_day_cannot_pay_for_one_more_game_play_is_paused_until_tomorrow(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        add_spend(conn, DAY, 0.75)  # $0.25 left, a game is estimated at $0.30
    state, reason = verdict(engine)
    assert state == "paused" and "today" in reason.lower() and "tomorrow" in reason.lower()


def test_exactly_enough_left_for_one_game_is_still_open(engine: Engine) -> None:
    with engine.begin() as conn:
        add_spend(conn, DAY, 0.70)  # $0.30 left
    assert verdict(engine)[0] == "open"


def test_a_new_day_resets_only_the_daily_number(engine: Engine) -> None:
    with engine.begin() as conn:
        add_spend(conn, DAY, 1.00)
    assert verdict(engine, day=DAY)[0] == "paused"
    assert verdict(engine, day=NEXT)[0] == "open"
    with engine.connect() as conn:
        assert round(spent_total(conn), 2) == 1.00  # yesterday still counts toward the total


def test_when_the_total_cannot_pay_for_one_more_game_play_is_closed(engine: Engine) -> None:
    with engine.begin() as conn:
        for day in ("2026-10-20", "2026-10-21", "2026-10-22"):
            add_spend(conn, day, 3.30)  # $9.90 in all, $0.10 left
    state, reason = verdict(engine, day=NEXT)
    assert state == "paused" and "total" in reason.lower()


def test_games_already_running_are_counted_against_what_is_left(engine: Engine) -> None:
    with engine.begin() as conn:
        add_spend(conn, DAY, 0.30)  # $0.70 left: two games in flight would use $0.60
    assert verdict(engine, running=1)[0] == "open"
    state, reason = verdict(engine, running=2)
    assert state == "busy" and "right now" in reason


def test_spending_is_kept_in_the_database_so_a_restart_forgets_nothing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'spend.db'}"
    first = make_engine(url)
    with first.begin() as conn:
        add_spend(conn, DAY, 0.90)
    first.dispose()
    second = make_engine(url)
    assert verdict(second)[0] == "paused"
