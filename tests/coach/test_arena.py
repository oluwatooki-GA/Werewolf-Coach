"""Champion against challenger on the same seeds, and the rule for changing the champion."""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from coach_support import MODEL, Rig

from werewolf.coach.arena import Arm, decide, play_arm
from werewolf.engine.roles import Team
from werewolf.engine.state import Settings

SEEDS = [1, 2, 3]
SETTINGS = Settings(summarize_rounds=True)


@pytest.fixture(autouse=True)
def in_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[2])  # the real cards/ folder


def arm(
    wins: int,
    games: int = 10,
    *,
    clean: bool = True,
    stopped: str | None = None,
    seeds: list[int] | None = None,
    card: str = "x",
) -> Arm:
    return Arm(card=card, side="wolf", seeds=seeds or list(range(games)), wins=wins, games=games,
               clean=clean, cost=Decimal("0"), logs=[], stopped=stopped)  # fmt: skip


@pytest.mark.parametrize(
    ("champion", "challenger", "promote"),
    [
        (5, 8, True),  # +30 points exactly
        (4, 7, True),
        (5, 7, False),  # +20
        (5, 5, False),  # a tie
        (6, 3, False),  # worse
        (0, 10, True),
    ],
)
def test_the_champion_changes_only_on_a_gap_of_thirty_points(
    champion: int, challenger: int, promote: bool
) -> None:
    verdict = decide(arm(champion), arm(challenger))
    assert verdict.promote is promote
    assert verdict.reason  # always says why, in words


def test_an_unclean_or_stopped_or_short_challenger_arm_is_never_promoted() -> None:
    assert not decide(arm(2), arm(9, clean=False)).promote
    assert "stopped" in decide(arm(2), arm(9, stopped="cap")).reason
    assert not decide(arm(2), arm(9, games=8, seeds=list(range(10)))).promote  # games missing


def test_a_champion_arm_that_is_short_of_games_is_not_beaten_on_fewer_games() -> None:
    verdict = decide(arm(0, games=3, seeds=list(range(10))), arm(3))
    assert not verdict.promote and "champion games finished" in verdict.reason


def test_arms_on_different_seeds_cannot_be_compared() -> None:
    with pytest.raises(ValueError, match="same seeds"):
        decide(arm(5, seeds=list(range(10))), arm(8, seeds=list(range(1, 11))))


def run(rig: Rig, tmp_path: Path, side: str, card: str) -> Arm:
    return asyncio.run(
        play_arm(
            rig.client, MODEL, side, card, SEEDS, settings=SETTINGS, data_dir=tmp_path / "games"
        )
    )


def test_both_arms_play_the_same_seeds_with_the_same_tables(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "rig")
    champion = run(rig, tmp_path / "a", "wolf", "wolf.accuse_early")
    challenger = run(rig, tmp_path / "b", "wolf", "wolf.lie_low")
    assert champion.seeds == challenger.seeds == SEEDS
    assert [log.seed for log in champion.logs] == [log.seed for log in challenger.logs] == SEEDS
    for one, two in zip(champion.logs, challenger.logs, strict=True):
        assert one.settings.personas == two.settings.personas  # same table manners
        assert [(p.name, p.role) for p in one.players] == [(p.name, p.role) for p in two.players]
    cards_a = {c.split("@")[0] for c in champion.logs[0].settings.cards.values()}
    cards_b = {c.split("@")[0] for c in challenger.logs[0].settings.cards.values()}
    assert cards_a == {"wolf.accuse_early"} and cards_b == {"wolf.lie_low"}


def test_only_the_tested_side_gets_the_card_and_win_counts_equal_the_logs(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path / "rig")
    wolves = run(rig, tmp_path / "w", "wolf", "wolf.lie_low")
    villagers = run(rig, tmp_path / "v", "villager", "villager.quiet_observer")
    for log in wolves.logs:
        roles = {p.name: p.role.value for p in log.players}
        assert {roles[s] for s in log.settings.cards} == {"Werewolf"}  # nobody else has a card
    for log in villagers.logs:
        roles = {p.name: p.role.value for p in log.players}
        assert {roles[s] for s in log.settings.cards} == {"Villager"}
    assert wolves.wins == sum(log.winner is Team.WOLVES for log in wolves.logs)
    assert villagers.wins == sum(log.winner is Team.VILLAGE for log in villagers.logs)
    assert wolves.games == villagers.games == len(SEEDS)


def test_a_spending_cap_stops_the_arm_and_blocks_promotion(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "rig", cap="0")
    blocked = run(rig, tmp_path, "wolf", "wolf.lie_low")
    assert blocked.stopped and blocked.games == 0 and rig.model.calls == []
    assert not decide(arm(5, games=3, seeds=SEEDS), blocked).promote


def test_the_cost_is_the_sum_of_the_games(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "rig")
    played = run(rig, tmp_path, "wolf", "wolf.lie_low")
    assert played.cost == sum((log.stats.cost for log in played.logs), Decimal("0")) > 0
