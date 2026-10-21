"""The record of each generation: saved whole, resumable, and readable as a family tree."""

from decimal import Decimal
from pathlib import Path

import pytest

from werewolf.coach.history import (
    ArmResult,
    CheckSummary,
    Generation,
    family_tree,
    last_complete,
    load_history,
    save_generation,
    total_cost,
)

D = Decimal


def arm(card: str, wins: int, games: int = 10, cost: str = "0.20") -> ArmResult:
    return ArmResult(card=card, seeds=list(range(games)), wins=wins, games=games, clean=True,
                     cost=D(cost), stopped=None)  # fmt: skip


def generation(
    number: int, *, promote: bool = False, champion: str = "wolf.accuse_early@2"
) -> Generation:
    challenger = f"wolf.coach_s1_g{number}@1"
    return Generation(
        side="wolf",
        number=number,
        champion_before=champion,
        champion_after=challenger if promote else champion,
        evidence="18 games, 5 lost, 4 shown",
        diagnosis="Wolves that accused in round 1 were voted out by round 2 in 13 of 27 seats. "
        "They should wait for a second message.",
        challenger_card=challenger,
        challenger_text="Wait for the second message, then accuse with a cite.",
        check=CheckSummary(attempts=2, passed=True, reasons=[["names a player (Ada)"]]),
        champion_arm=arm(champion, 5),
        challenger_arm=arm(challenger, 8 if promote else 6),
        promote=promote,
        decision="clear win" if promote else "not clear yet",
        coach_cost=D("0.15"),
    )


def test_a_generation_round_trips_exactly_and_is_saved_where_the_side_expects(
    tmp_path: Path,
) -> None:
    gen = generation(1)
    path = save_generation(gen, tmp_path)
    assert path == tmp_path / "wolf" / "gen-001.json"
    assert load_history("wolf", tmp_path) == [gen]


def test_a_finished_generation_is_never_overwritten(tmp_path: Path) -> None:
    save_generation(generation(1), tmp_path)
    with pytest.raises(ValueError, match="already saved"):
        save_generation(generation(1, promote=True), tmp_path)


def test_a_half_written_file_is_not_a_finished_generation(tmp_path: Path) -> None:
    save_generation(generation(1), tmp_path)
    (tmp_path / "wolf" / "gen-002.json").write_text('{"side": "wolf", "number": 2, "cham', "utf-8")
    assert [g.number for g in load_history("wolf", tmp_path)] == [1]
    assert last_complete("wolf", tmp_path) == 1  # a crash resumes at generation 2


def test_last_complete_is_zero_for_a_new_side_and_stops_at_the_first_gap(tmp_path: Path) -> None:
    assert last_complete("wolf", tmp_path) == 0
    save_generation(generation(1), tmp_path)
    save_generation(generation(3), tmp_path)  # generation 2 is missing
    assert last_complete("wolf", tmp_path) == 1


def test_sides_are_kept_apart(tmp_path: Path) -> None:
    save_generation(generation(1), tmp_path)
    assert load_history("villager", tmp_path) == []


def test_the_family_tree_shows_each_card_its_diagnosis_both_results_and_the_verdict(
    tmp_path: Path,
) -> None:
    save_generation(generation(1, promote=True), tmp_path)
    save_generation(generation(2, champion="wolf.coach_s1_g1@1"), tmp_path)
    tree = family_tree("wolf", tmp_path)
    assert "wolf.accuse_early@2" in tree.splitlines()[0]  # where the line started
    assert "Generation 1" in tree and "wolf.coach_s1_g1@1" in tree and "kept" in tree
    assert "Generation 2" in tree and "dropped" in tree
    assert "5/10" in tree and "8/10" in tree and "6/10" in tree
    assert "Wolves that accused in round 1" in tree


def test_an_empty_family_tree_says_so(tmp_path: Path) -> None:
    assert "no generations yet" in family_tree("villager", tmp_path)


def test_costs_add_up_across_generations(tmp_path: Path) -> None:
    save_generation(generation(1), tmp_path)
    save_generation(generation(2), tmp_path)
    # each generation: coach 0.15, two arms 0.20 each
    assert total_cost("wolf", tmp_path) == D("1.10")


def test_a_challenger_that_never_passed_its_checks_is_recorded_without_arms(tmp_path: Path) -> None:
    gen = generation(1).model_copy(
        update={
            "challenger_card": None,
            "challenger_arm": None,
            "champion_arm": None,
            "check": CheckSummary(attempts=3, passed=False, reasons=[["a"], ["b"], ["c"]]),
            "decision": "no valid challenger: dropped without playing",
        }
    )
    save_generation(gen, tmp_path)
    tree = family_tree("wolf", tmp_path)
    assert "no valid challenger" in tree and "never played" in tree
    assert total_cost("wolf", tmp_path) == D("0.15")
