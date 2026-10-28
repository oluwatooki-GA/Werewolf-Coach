"""The prompt wording lives in YAML; these tests keep the files and the loader honest."""

import re
from string import Template

import pytest

from werewolf.prompts import DIR, load, text
from werewolf.tagger.moves import MOVE_NAMES

FILES = sorted(p.stem for p in DIR.glob("*.yaml"))


def test_every_prompt_file_has_a_version() -> None:
    assert FILES == ["coach", "grounding", "leakguard", "moves", "player", "tagger"]
    for name in FILES:
        assert isinstance(load(name)["version"], int)


def test_text_fills_placeholders_and_refuses_a_missing_one() -> None:
    assert text("player", "intro", name="Ada", seats="Ada, Bo") == (
        "You are Ada, a player in a game of Werewolf with 8 players: Ada, Bo."
    )
    with pytest.raises(KeyError):
        text("player", "intro", name="Ada")  # ${seats} was not given


def test_text_may_use_a_placeholder_called_name() -> None:
    # the loader's own arguments must not collide with the words a prompt uses
    assert "Ada" in text("player", "intro", name="Ada", seats="x")


def test_every_placeholder_in_player_yaml_is_a_plain_word() -> None:
    strings = {k: v for k, v in load("player").items() if isinstance(v, str)}
    assert len(strings) > 30
    for key, value in strings.items():
        names = Template(value).get_identifiers()
        assert all(re.fullmatch(r"[a-z_]+", n) for n in names), key


def test_the_eleven_moves_load_with_a_family_meaning_and_example() -> None:
    moves = load("moves")["moves"]
    assert [m["name"] for m in moves] == list(MOVE_NAMES) and len(moves) == 11
    assert all(m["family"] and m["what"] and m["example"] for m in moves)


def test_the_files_ship_with_the_package() -> None:
    assert (DIR / "player.yaml").is_file() and (DIR / "__init__.py").is_file()


def test_players_are_told_not_to_repeat_a_question_already_asked() -> None:
    assert "Do not ask a question someone has already asked" in text(
        "player", "reminders", reason_max=40, note_max=100, belief_rule=""
    )


def test_version_two_rules_are_in_the_text_and_the_defaults() -> None:
    from werewolf.engine.state import Settings

    rules = text("player", "speaking_floor_tokens", turns=10, tokens="4 floor tokens", max_bid=4)
    assert "accuses or questions someone" in rules and "bid 0" in rules
    assert (Settings().speaking_turns, Settings().tokens_per_day) == (10, 4)
    reminders = text("player", "reminders", reason_max=40, note_max=100, belief_rule="")
    assert "no dashes" in reminders and "not X but Y" in reminders


def test_wolves_are_told_not_to_accuse_their_partner_and_players_not_to_use_stock_lines() -> None:
    from werewolf.agents.prompt import ROLE_TEXT
    from werewolf.engine.roles import Role

    assert "do not accuse your partner or vote for them" in " ".join(
        ROLE_TEXT[Role.WEREWOLF].split()
    )
    reminders = " ".join(
        text("player", "reminders", reason_max=40, note_max=100, belief_rule="").split()
    )
    assert "stock lines" in reminders and "say what the player actually did or said" in reminders
