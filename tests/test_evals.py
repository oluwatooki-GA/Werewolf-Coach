"""The eval check: recorded games replayed with no model, measured, and held to a baseline."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from werewolf.cli import main
from werewolf.engine.log import GameLog
from werewolf.evals import Measures, compare, measure, table

ROOT = Path(__file__).resolve().parent.parent
GAMES = ROOT / "evals" / "games"
BASELINE = ROOT / "evals" / "baseline.json"


def baseline() -> Measures:
    return Measures.from_json(BASELINE.read_text(encoding="utf-8"))


GOOD = Measures(
    games=8,
    responses=1000,
    rejected=40,
    replay_errors=0,
    leaks=0,
    adherence={"wolf.lie_low": (30, 50), "villager.track_votes": (20, 40)},
)


# --- the committed set ---------------------------------------------------------------------


def test_the_recorded_games_are_the_fixed_set_and_the_baseline_describes_them() -> None:
    assert len(list(GAMES.glob("*.json"))) == 16  # 8 games and their 8 tag files
    assert baseline().games == 8


def test_the_code_as_it_stands_meets_its_own_baseline() -> None:
    now = measure(GAMES)
    assert compare(baseline(), now) == []
    assert now.replay_errors == 0 and now.leaks == 0


def test_measuring_twice_gives_the_same_numbers() -> None:
    assert measure(GAMES) == measure(GAMES)


def test_no_model_is_called(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(**kwargs: object) -> None:
        raise AssertionError("a model call was made")

    monkeypatch.setattr("litellm.acompletion", forbidden)
    assert measure(GAMES).games == 8


# --- what counts as worse ------------------------------------------------------------------


def test_the_same_numbers_are_fine_and_better_numbers_are_fine() -> None:
    assert compare(GOOD, GOOD) == []
    better = replace(
        GOOD, rejected=10, adherence={"wolf.lie_low": (40, 50), "villager.track_votes": (20, 40)}
    )
    assert compare(GOOD, better) == []


def test_more_rejected_answers_is_worse() -> None:
    (problem,) = compare(GOOD, replace(GOOD, rejected=41))
    assert "rejected" in problem and "40" in problem and "41" in problem


def test_the_rate_not_the_count_is_what_is_held() -> None:
    more_answers = replace(GOOD, responses=2000, rejected=70)  # 3.5%, below the 4%
    assert compare(GOOD, more_answers) == []


def test_a_prompt_that_leaks_a_secret_is_worse() -> None:
    (problem,) = compare(GOOD, replace(GOOD, leaks=1))
    assert "leak" in problem


def test_a_game_that_no_longer_replays_is_worse() -> None:
    (problem,) = compare(GOOD, replace(GOOD, replay_errors=1))
    assert "replay" in problem


def test_a_card_that_is_followed_less_by_more_than_five_points_is_worse() -> None:
    small = replace(GOOD, adherence={**GOOD.adherence, "wolf.lie_low": (27, 50)})  # 60% -> 54%
    (problem,) = compare(GOOD, small)
    assert "wolf.lie_low" in problem
    ok = replace(GOOD, adherence={**GOOD.adherence, "wolf.lie_low": (28, 50)})  # 60% -> 56%
    assert compare(GOOD, ok) == []


def test_a_card_that_is_no_longer_measured_is_a_problem_not_a_pass() -> None:
    gone = replace(GOOD, adherence={"wolf.lie_low": (30, 50)})
    (problem,) = compare(GOOD, gone)
    assert "villager.track_votes" in problem


def test_a_changed_set_of_games_asks_for_a_new_baseline() -> None:
    (problem,) = compare(GOOD, replace(GOOD, games=7))
    assert "baseline" in problem


def test_the_table_puts_before_beside_after_and_says_which_way_each_went() -> None:
    text = table(GOOD, replace(GOOD, rejected=50, leaks=0))
    assert text.startswith("| Measure | Before | After |")
    assert "40 of 1000" in text and "50 of 1000" in text
    assert "worse" in text and "same" in text


# --- the command ---------------------------------------------------------------------------


def test_the_command_passes_on_the_committed_games_and_prints_the_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["evals", "--games", str(GAMES), "--baseline", str(BASELINE)]) == 0
    assert "| Measure | Before | After |" in capsys.readouterr().out


def test_the_command_fails_when_a_recorded_game_is_made_worse_on_purpose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    games = tmp_path / "games"
    shutil.copytree(GAMES, games)
    path = next(p for p in sorted(games.glob("*.json")) if not p.name.endswith(".tags.json"))
    log = GameLog.from_json(path.read_text(encoding="utf-8"))
    call = next(c for c in log.calls if c.rejected == 0 and not c.failed)
    call.responses[0] = "this is not an answer"  # one valid answer replaced with garbage
    path.write_text(log.to_json(), encoding="utf-8")
    assert main(["evals", "--games", str(games), "--baseline", str(BASELINE)]) == 1
    assert "worse" in capsys.readouterr().out


def test_the_baseline_can_be_rewritten_and_then_passes(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    assert (
        main(["evals", "--games", str(GAMES), "--baseline", str(target), "--write-baseline"]) == 0
    )
    assert json.loads(target.read_text(encoding="utf-8"))["games"] == 8
    assert main(["evals", "--games", str(GAMES), "--baseline", str(target)]) == 0


def test_a_missing_baseline_is_an_error_not_a_pass(tmp_path: Path) -> None:
    assert main(["evals", "--games", str(GAMES), "--baseline", str(tmp_path / "nope.json")]) == 2


def test_a_recorded_answer_cut_off_mid_json_does_not_stop_the_prompts_being_rebuilt() -> None:
    from werewolf.promptview import rebuild

    # the Sonnet game has an answer that starts as JSON and was cut off before it ended
    log = GameLog.from_json((GAMES / "13-8f572fbb.json").read_text(encoding="utf-8"))
    assert any(
        r.startswith("{") and not r.rstrip().endswith("}")
        for c in log.calls
        for r in c.responses
        if isinstance(r, str)
    )
    assert len(rebuild(log)) > 100
