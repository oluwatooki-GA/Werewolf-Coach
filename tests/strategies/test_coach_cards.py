"""Cards the coach writes: saved beside the starters, found by id, and never naming a player."""

from pathlib import Path

import pytest

from werewolf.engine.roles import Role
from werewolf.strategies.cards import (
    Card,
    check_card,
    load_all,
    load_card,
    write_card,
)

REPO_CARDS = Path(__file__).resolve().parents[2] / "cards"


def card(**change: object) -> Card:
    base: dict[str, object] = {
        "id": "wolf.coach_s1_g1",
        "version": 1,
        "role": Role.WEREWOLF,
        "source": "the coach, generation 1",
        "summary": "Pressure the quiet.",
        "instructions": "Bid 2 or 3. Accuse the player who has said least, with the line you cite.",
        "expected_moves": ("accuse_reasoned", "rally"),
    }
    return Card.model_validate({**base, **change})


def test_a_written_card_loads_back_equal_from_the_coach_folder(tmp_path: Path) -> None:
    path = write_card(card(), tmp_path)
    assert path == tmp_path / "coach" / "wolf.coach_s1_g1.yaml"
    assert load_card("wolf.coach_s1_g1", tmp_path) == card()
    assert load_card("wolf.coach_s1_g1@1", tmp_path) == card()


def test_starter_cards_and_coach_cards_are_found_by_the_same_loader(tmp_path: Path) -> None:
    (tmp_path / "wolf.starter.yaml").write_text(
        "id: wolf.starter\nversion: 1\nrole: Werewolf\nsource: s\nsummary: s\n"
        "instructions: Be quiet.\nexpected_moves: [hedge]\n",
        encoding="utf-8",
    )
    write_card(card(), tmp_path)
    assert load_card("wolf.starter", tmp_path).id == "wolf.starter"
    assert load_card("wolf.coach_s1_g1", tmp_path).id == "wolf.coach_s1_g1"
    assert list(load_all(tmp_path)) == ["wolf.starter"]  # load_all stays the starters only


def test_the_twelve_starters_are_still_exactly_twelve_even_with_a_coach_folder() -> None:
    assert len(load_all(REPO_CARDS)) == 12
    assert all(check_card(c) == [] for c in load_all(REPO_CARDS).values())


def test_an_id_used_in_both_folders_is_refused(tmp_path: Path) -> None:
    write_card(card(), tmp_path)
    (tmp_path / "wolf.coach_s1_g1.yaml").write_text(
        (tmp_path / "coach" / "wolf.coach_s1_g1.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="used by another card"):
        load_card("wolf.coach_s1_g1", tmp_path)


def test_a_card_is_never_overwritten(tmp_path: Path) -> None:
    write_card(card(), tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        write_card(card(summary="Something else."), tmp_path)


@pytest.mark.parametrize("name", ["Ada", "Bo", "Cy", "Di", "Eve", "Fay", "Gus", "Hal"])
def test_a_card_that_names_a_player_fails(name: str) -> None:
    problems = check_card(card(instructions=f"Always accuse {name} first, with a reason."))
    assert any("names a player" in p and name in p for p in problems)


def test_words_that_only_contain_a_name_are_fine() -> None:
    text = "Even the bold can listen. Dialogue and halting speech are fine."
    assert check_card(card(instructions=text)) == []


def test_a_written_card_that_fails_the_checks_is_refused_before_it_is_saved(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="names a player"):
        write_card(card(instructions="Blame Ada."), tmp_path)
    assert not (tmp_path / "coach").exists()
