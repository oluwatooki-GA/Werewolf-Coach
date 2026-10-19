from pathlib import Path

import pytest

from werewolf.engine.roles import Role
from werewolf.strategies.cards import assign_cards, check_card, load_all, load_card
from werewolf.tagger.moves import MOVE_NAMES

GOOD = """\
id: wolf.lie_low
version: 1
role: Werewolf
source: test
summary: Stay unnoticed.
instructions: >
  Speak rarely and bid low. Agree with whoever the majority suspects.
expected_moves: [hedge, self_defend]
"""


def write(folder: Path, name: str, text: str) -> None:
    (folder / name).write_text(text, encoding="utf-8")


def bad(tmp_path: Path, **change: str) -> str:
    """The good card with one line swapped, loaded and checked; returns the error text."""
    text = GOOD
    for key, value in change.items():
        start = text.index(f"{key}:")
        end = text.index("\n", start)
        if key == "instructions":
            end = text.index("expected_moves:") - 1
        text = text[:start] + f"{key}: {value}" + text[end:]
    write(tmp_path, "c.yaml", text)
    with pytest.raises(ValueError) as caught:
        load_all(tmp_path)
    return str(caught.value)


def test_a_valid_card_loads_by_id(tmp_path: Path) -> None:
    write(tmp_path, "wolf.lie_low.yaml", GOOD)
    card = load_card("wolf.lie_low", tmp_path)
    assert card.role is Role.WEREWOLF and card.ref == "wolf.lie_low@1"
    assert card.prompt_text.startswith("Speak rarely")
    assert load_card("wolf.lie_low@1", tmp_path) == card


def test_an_unknown_id_names_the_cards_that_exist(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", GOOD)
    with pytest.raises(ValueError, match="wolf.lie_low"):
        load_card("wolf.nope", tmp_path)


def test_too_many_words_fails(tmp_path: Path) -> None:
    assert "81 words" in bad(tmp_path, instructions=" ".join(["word"] * 81))


def test_an_id_with_the_wrong_prefix_fails(tmp_path: Path) -> None:
    assert "must start with 'wolf.'" in bad(tmp_path, id="seer.lie_low")


def test_an_unknown_move_fails(tmp_path: Path) -> None:
    assert "unknown moves" in bad(tmp_path, expected_moves="[shout]")


def test_an_empty_source_fails(tmp_path: Path) -> None:
    assert "source is empty" in bad(tmp_path, source='""')


def test_a_missing_field_names_the_file(tmp_path: Path) -> None:
    write(tmp_path, "c.yaml", GOOD.replace("summary: Stay unnoticed.\n", ""))
    with pytest.raises(ValueError, match="c.yaml"):
        load_all(tmp_path)


def test_a_villager_card_cannot_lean_on_wolf_knowledge(tmp_path: Path) -> None:
    text = GOOD.replace("wolf.lie_low", "villager.quiet").replace("Werewolf", "Villager")
    write(tmp_path, "c.yaml", text.replace("Agree with", "Back your partner and agree with"))
    with pytest.raises(ValueError, match="wolf-only"):
        load_all(tmp_path)


def test_a_duplicate_id_fails(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", GOOD)
    write(tmp_path, "b.yaml", GOOD)
    with pytest.raises(ValueError, match="used by another card"):
        load_all(tmp_path)


def test_check_card_returns_problems_without_raising(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", GOOD)
    assert check_card(load_card("wolf.lie_low", tmp_path)) == []


def test_every_move_in_the_move_list_is_unique() -> None:
    assert len(set(MOVE_NAMES)) == len(MOVE_NAMES) == 11


def test_assign_by_role_then_seat_and_wrong_role(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", GOOD)
    roles = {"Ada": Role.WEREWOLF, "Bo": Role.WEREWOLF, "Cy": Role.SEER}
    assert assign_cards(roles, {Role.WEREWOLF: "wolf.lie_low"}, {}, tmp_path) == {
        "Ada": "wolf.lie_low@1",
        "Bo": "wolf.lie_low@1",
    }
    with pytest.raises(ValueError, match="Seer"):
        assign_cards(roles, {}, {"Cy": "wolf.lie_low"}, tmp_path)
    with pytest.raises(ValueError, match="no seat"):
        assign_cards(roles, {}, {"Zed": "wolf.lie_low"}, tmp_path)
