import json
import subprocess
import sys
from pathlib import Path

import pytest

from werewolf.cli import main
from werewolf.engine.log import GameLog, replays_exactly


def play(tmp_path: Path, *extra: str) -> int:
    return main(
        ["play", "--seed", "1", "--agents", "scripted", "--data-dir", str(tmp_path), *extra]
    )


def saved(tmp_path: Path) -> Path:
    (path,) = tmp_path.glob("*.json")
    return path


def test_play_writes_a_game_log_and_prints_a_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert play(tmp_path) == 0
    out = capsys.readouterr().out
    assert "Village won in 2 rounds" in out
    assert "rejected 0 of" in out and "(0.0%)" in out
    assert "clean: yes" in out
    log = GameLog.from_json(saved(tmp_path).read_text(encoding="utf-8"))
    assert log.seed == 1 and replays_exactly(log)


def test_the_file_name_is_the_seed_and_a_hash_of_the_log(tmp_path: Path) -> None:
    play(tmp_path)
    assert saved(tmp_path).name.startswith("1-") and saved(tmp_path).suffix == ".json"
    play(tmp_path)  # the same game again lands on the same file
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_the_file_uses_unix_line_endings_even_on_windows(tmp_path: Path) -> None:
    play(tmp_path)
    data = saved(tmp_path).read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")


def test_a_speaking_mode_can_be_chosen(tmp_path: Path) -> None:
    assert play(tmp_path, "--speaking-mode", "fixed_order") == 0
    log = GameLog.from_json(saved(tmp_path).read_text(encoding="utf-8"))
    assert log.settings.speaking_mode == "fixed_order"


def test_replay_reports_an_exact_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    play(tmp_path)
    capsys.readouterr()
    assert main(["replay", str(saved(tmp_path))]) == 0
    assert "exact match" in capsys.readouterr().out


def test_replay_fails_when_the_log_was_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    play(tmp_path)
    path = saved(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["seed"] = 2
    path.write_bytes((json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode())
    capsys.readouterr()
    assert main(["replay", str(path)]) == 1
    assert "DIFFERENT" in capsys.readouterr().out


def test_replay_of_a_missing_or_broken_file_is_an_error_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["replay", str(tmp_path / "nope.json")]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert main(["replay", str(broken)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_it_runs_as_a_module(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "werewolf.cli", "play", "--seed", "1", "--agents", "scripted",
         "--data-dir", str(tmp_path)],
        capture_output=True,
        text=True,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert "Village won" in result.stdout
