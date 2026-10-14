"""Model-driven games from the command line, with a fake model behind the real client."""

from decimal import Decimal
from pathlib import Path

import pytest
from test_llm_agent import MODEL, Rig

from werewolf import runner, runtime
from werewolf.audit import Leak
from werewolf.cli import main
from werewolf.engine.log import GameLog, replays_exactly
from werewolf.llm.client import LLMClient

D = Decimal
Built = list[tuple[str, Decimal | None]]


def install(rig: Rig, monkeypatch: pytest.MonkeyPatch, built: Built) -> None:
    """Where the CLI would build a real client, hand it this one."""

    def fake_build(model: str, max_spend: Decimal | None, **kw: object) -> LLMClient:
        built.append((model, max_spend))
        return rig.client

    monkeypatch.setattr(runtime, "build_client", fake_build)


@pytest.fixture
def built() -> Built:
    return []


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: Built) -> Rig:
    rig = Rig(tmp_path / "rig")
    install(rig, monkeypatch, built)
    return rig


def batch(tmp_path: Path, *args: str) -> int:
    base = ["batch", "--model", MODEL, "--max-spend", "1.00", "--data-dir", str(tmp_path / "games")]
    return main([*base, *args])


def saved(tmp_path: Path) -> list[GameLog]:
    files = sorted((tmp_path / "games").glob("*.json"))
    return [GameLog.from_json(p.read_text(encoding="utf-8")) for p in files]


def test_a_batch_plays_every_game_saves_each_log_and_prints_one_report(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = batch(tmp_path, "--games", "3", "--first-seed", "1", "--parallel", "2")
    out = capsys.readouterr().out
    logs = saved(tmp_path)
    assert code == 0
    assert sorted(log.seed for log in logs) == [1, 2, 3]
    assert all(replays_exactly(log) for log in logs)
    assert "games: 3 finished, 0 stopped" in out and "leaks: 0" in out


def test_the_report_numbers_equal_the_sums_over_the_saved_logs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch(tmp_path, "--games", "3", "--parallel", "2")
    out = capsys.readouterr().out
    logs = saved(tmp_path)
    responses = sum(log.stats.responses for log in logs)
    rejected = sum(log.stats.rejected for log in logs)
    prompt = sum(log.stats.prompt_tokens for log in logs)
    completion = sum(log.stats.completion_tokens for log in logs)
    cached = sum(log.stats.cached_tokens for log in logs)
    cost = sum((log.stats.cost for log in logs), D("0"))
    assert f"rejected {rejected} of {responses}" in out
    assert f"input {prompt:,}" in out and f"output {completion:,}" in out
    assert f"({round(100 * cached / prompt)}% cached)" in out
    assert f"${cost:.6f} total" in out
    assert f"${cost / 3:.6f} per game" in out
    assert cost == rig.ledger.spent("openai") > 0


def test_each_game_gets_its_own_run_id_and_real_runs_ask_for_summaries(
    rig: Rig, tmp_path: Path
) -> None:
    batch(tmp_path, "--games", "3")
    logs = saved(tmp_path)
    assert len({log.run_id for log in logs}) == 3 and all(log.run_id for log in logs)
    assert all(log.settings.summarize_rounds for log in logs)


def test_each_finished_game_prints_a_progress_line(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch(tmp_path, "--games", "2", "--first-seed", "5")
    out = capsys.readouterr().out
    assert "seed 5:" in out and "seed 6:" in out and "won in" in out


def test_in_fresh_mode_the_same_seed_twice_asks_the_model_both_times(
    rig: Rig, tmp_path: Path
) -> None:
    batch(tmp_path, "--games", "1", "--first-seed", "1")
    first_calls, first_spent = len(rig.model.calls), rig.ledger.spent("openai")
    batch(tmp_path, "--games", "1", "--first-seed", "1")
    assert len(rig.model.calls) == 2 * first_calls
    assert rig.ledger.spent("openai") == 2 * first_spent
    assert len(saved(tmp_path)) == 2


def test_in_shared_mode_a_repeat_is_served_from_the_cache_for_free(
    rig: Rig, tmp_path: Path
) -> None:
    batch(tmp_path, "--games", "1", "--first-seed", "1", "--cache", "shared")
    first_calls, first_spent = len(rig.model.calls), rig.ledger.spent("openai")
    batch(tmp_path, "--games", "1", "--first-seed", "1", "--cache", "shared")
    assert len(rig.model.calls) == first_calls
    assert rig.ledger.spent("openai") == first_spent
    logs = saved(tmp_path)
    assert len(logs) == 2 and logs[0].events == logs[1].events


def test_the_model_and_spending_limit_reach_the_client_builder(
    rig: Rig, tmp_path: Path, built: Built
) -> None:
    batch(tmp_path, "--games", "1")
    assert built == [(MODEL, D("1.00"))]


def test_the_requests_per_minute_option_reaches_the_client_builder(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []

    def capture(model: str, max_spend: Decimal | None, **kw: object) -> LLMClient:
        seen.append(kw.get("requests_per_minute"))
        return rig.client

    monkeypatch.setattr(runtime, "build_client", capture)
    batch(tmp_path, "--games", "1", "--rpm", "7")
    batch(tmp_path, "--games", "1")
    assert seen == [7, None]


def test_a_spent_cap_stops_the_batch_reports_what_finished_and_exits_non_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    built: Built,
    capsys: pytest.CaptureFixture[str],
) -> None:
    small = Rig(tmp_path / "small", cap="0.0000025")  # room for one call only
    install(small, monkeypatch, built)
    code = batch(tmp_path, "--games", "3", "--parallel", "1")
    out = capsys.readouterr()
    assert code == 1
    assert "0 finished, 1 stopped" in out.out  # the first game was cut short...
    assert "2 game(s) not started" in out.out  # ...and the other two were never begun
    assert "spending" in (out.out + out.err).lower() or "cap" in (out.out + out.err).lower()
    assert saved(tmp_path) == []  # an interrupted game is not saved as if it were finished


def test_a_paid_model_without_a_spending_limit_is_refused_before_any_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["batch", "--model", "gpt-4.1-nano", "--games", "1", "--data-dir", str(tmp_path)])
    assert code == 2
    assert "--max-spend" in capsys.readouterr().err


def test_any_leak_makes_the_batch_fail(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        runner, "find_leaks", lambda log, prompts, **kw: [Leak("Cy", "note", "x" * 20)]
    )
    code = batch(tmp_path, "--games", "1")
    out = capsys.readouterr().out
    assert code == 1 and "leaks: 1" in out and "note" in out and "Cy" in out


def test_play_with_llm_agents_plays_and_saves_one_game(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["play", "--agents", "llm", "--model", MODEL, "--max-spend", "1.00", "--seed", "2",
         "--data-dir", str(tmp_path / "games")]
    )  # fmt: skip
    assert code == 0
    assert [log.seed for log in saved(tmp_path)] == [2]
    assert "won in" in capsys.readouterr().out


def test_play_with_llm_agents_needs_a_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["play", "--agents", "llm", "--data-dir", str(tmp_path)]) == 2
    assert "--model" in capsys.readouterr().err


def test_notes_option_turns_on_the_scratchpad_and_keeps_the_audit_clean(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert batch(tmp_path, "--games", "1", "--notes", "3") == 0
    assert "leaks: 0" in capsys.readouterr().out
    shown = [r for r in rig.model.calls if "Your recent private notes" in r.messages[1]["content"]]
    assert shown


def test_without_the_notes_option_no_prompt_has_a_notes_section(rig: Rig, tmp_path: Path) -> None:
    batch(tmp_path, "--games", "1")
    assert not [r for r in rig.model.calls if "private notes" in r.messages[1]["content"]]
