"""Strategy cards chosen on the command line reach the right players' prompts and the game log."""

from pathlib import Path

import pytest
from test_cli_llm import batch, install, saved
from test_llm_agent import Rig, player_of

from werewolf.cli import main
from werewolf.engine.log import replays_exactly
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.promptview import rebuild

WOLF = """\
id: wolf.lie_low
version: 1
role: Werewolf
source: test
summary: Stay unnoticed.
instructions: Speak rarely and agree with the majority.
expected_moves: [hedge]
"""
SEER = WOLF.replace("wolf.lie_low", "seer.reveal").replace("Werewolf", "Seer")
WOLF_TEXT = "Speak rarely and agree with the majority."


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    rig = Rig(tmp_path / "rig")
    install(rig, monkeypatch, [])
    folder = tmp_path / "cards"
    folder.mkdir()
    (folder / "wolf.lie_low.yaml").write_text(WOLF, encoding="utf-8")
    (folder / "seer.reveal.yaml").write_text(SEER, encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # cards are read from ./cards
    return rig


def roles(seed: int) -> dict[str, Role]:
    return {p.name: p.role for p in new_game(seed).players}


def system_of(rig: Rig, name: str) -> str:
    return next(r.messages[0]["content"] for r in rig.model.calls if player_of(r) == name)


def test_a_role_card_reaches_only_that_roles_prompts_and_the_log(rig: Rig, tmp_path: Path) -> None:
    assert batch(tmp_path, "--first-seed", "1", "--cards", "wolf=wolf.lie_low") == 0
    (log,) = saved(tmp_path)
    wolves = [n for n, r in roles(1).items() if r is Role.WEREWOLF]
    assert log.settings.cards == {w: "wolf.lie_low@1" for w in wolves}
    for name in roles(1):
        assert (WOLF_TEXT in system_of(rig, name)) == (name in wolves)
    assert replays_exactly(log)


def test_two_roles_can_be_set_at_once(rig: Rig, tmp_path: Path) -> None:
    seer = next(n for n, r in roles(1).items() if r is Role.SEER)
    batch(tmp_path, "--cards", "wolf=wolf.lie_low,seer=seer.reveal")
    (log,) = saved(tmp_path)
    assert log.settings.cards[seer] == "seer.reveal@1" and len(log.settings.cards) == 3
    seat = next(n for n, r in roles(1).items() if r is Role.WEREWOLF)
    assert batch(tmp_path, "--card-seat", f"{seat}=wolf.lie_low") == 0


def test_with_no_cards_the_log_and_prompts_are_as_before(rig: Rig, tmp_path: Path) -> None:
    batch(tmp_path)
    (log,) = saved(tmp_path)
    assert log.settings.cards == {}
    assert all(WOLF_TEXT not in r.messages[0]["content"] for r in rig.model.calls)


def test_a_card_for_the_wrong_seat_stops_the_run_before_any_call(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    villager = next(n for n, r in roles(1).items() if r is Role.VILLAGER)
    assert batch(tmp_path, "--card-seat", f"{villager}=wolf.lie_low") == 2
    assert "cannot start" in capsys.readouterr().err and rig.model.calls == []


def test_a_bad_card_file_or_option_stops_the_run_before_any_call(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "cards" / "wolf.long.yaml").write_text(
        WOLF.replace("wolf.lie_low", "wolf.long").replace(WOLF_TEXT, "word " * 90),
        encoding="utf-8",
    )
    assert batch(tmp_path, "--cards", "wolf=wolf.lie_low") == 2
    assert "90 words" in capsys.readouterr().err
    assert batch(tmp_path, "--cards", "bear=wolf.lie_low") == 2
    assert batch(tmp_path, "--cards", "wolf=wolf.missing") == 2
    assert rig.model.calls == []


def test_scripted_games_refuse_cards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["play", "--agents", "scripted", "--cards", "wolf=wolf.lie_low"]) == 2
    assert "need --agents llm" in capsys.readouterr().err


def test_rebuilt_prompts_show_the_card(rig: Rig, tmp_path: Path) -> None:
    batch(tmp_path, "--cards", "wolf=wolf.lie_low")
    (log,) = saved(tmp_path)
    wolf = next(iter(log.settings.cards))
    first = next(i for i in rebuild(log) if i.player == wolf)
    assert WOLF_TEXT in first.messages[0]["content"]
