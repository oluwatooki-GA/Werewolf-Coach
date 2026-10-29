"""How long the talking is can be set from the command line."""

from pathlib import Path

import pytest

from werewolf.cli import main
from werewolf.engine.log import GameLog
from werewolf.engine.state import Settings
from werewolf.runtime import default_max_tokens


def played(tmp_path: Path, *args: str) -> GameLog:
    assert main(["play", "--data-dir", str(tmp_path), *args]) == 0
    (path,) = tmp_path.glob("*.json")
    return GameLog.from_json(path.read_text(encoding="utf-8"))


def test_the_talking_length_can_be_set(tmp_path: Path) -> None:
    log = played(tmp_path, "--turns", "3", "--tokens-per-day", "2", "--message-chars", "120")
    assert (log.settings.speaking_turns, log.settings.tokens_per_day) == (3, 2)
    assert log.settings.max_message_chars == 120


def test_without_options_the_game_keeps_its_usual_settings_and_the_new_wolf_chat(
    tmp_path: Path,
) -> None:
    assert played(tmp_path).settings == Settings(wolf_chat_messages=5)


def test_the_wolf_chat_limit_can_be_set_and_zero_is_the_old_night(tmp_path: Path) -> None:
    assert played(tmp_path, "--wolf-chat", "3").settings.wolf_chat_messages == 3
    for old in tmp_path.glob("*.json"):
        old.unlink()
    assert played(tmp_path, "--wolf-chat", "0").settings == Settings()


@pytest.mark.parametrize(
    "option",
    [["--turns", "0"], ["--turns", "41"], ["--message-chars", "10"], ["--tokens-per-day", "0"]],
)
def test_values_outside_the_allowed_range_are_refused(option: list[str], tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["play", "--data-dir", str(tmp_path), *option])
    assert not list(tmp_path.glob("*.json"))


def test_longer_messages_get_more_output_room() -> None:
    assert default_max_tokens("claude-haiku-5-5", 900) == 1200
    assert default_max_tokens("gpt-4.1-nano", 600) == 400
    assert default_max_tokens("gpt-4.1-nano", 100) == 300  # shorter never goes below the base
