"""What the batch report says about fact-checks, rewrites and why answers were turned down."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from test_cli_llm import batch, install, saved
from test_llm_agent import Rig

from werewolf.agents.leakguard import REWRITE


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    rig = Rig(tmp_path / "rig")
    rig.model.talk = True  # players speak, so there is something to check
    install(rig, monkeypatch, [])
    return rig


def checks(rig: Rig) -> list[str]:
    return [r.model for r in rig.model.calls if r.schema_ and r.schema_["title"] == "WireGround"]


def test_every_game_is_fact_checked_by_default_and_the_cost_is_in_the_total(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert batch(tmp_path, "--games", "2") == 0
    out = capsys.readouterr().out
    assert checks(rig) and re.search(r"unsupported claims 0 of \d+ messages \(0%\)", out)
    total = Decimal(re.search(r"cost: \$([\d.]+) total", out).group(1))  # type: ignore[union-attr]
    assert total == rig.ledger.spent("openai")  # games, guards and fact-checks, all counted
    assert "the fact-check is $" in out


def test_the_check_can_be_turned_off_or_given_its_own_model(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch(tmp_path, "--no-claim-check")
    assert checks(rig) == [] and "claims not checked" in capsys.readouterr().out
    batch(tmp_path, "--claim-check-model", "gpt-4.1-mini")
    assert set(checks(rig)) == {"gpt-4.1-mini"}


def test_flagged_claims_are_counted(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.model.raw["WireGround"] = json.dumps({"unsupported": "made up"})
    batch(tmp_path)
    assert re.search(r"unsupported claims (\d+) of \1 messages \(100%\)", capsys.readouterr().out)


def test_rewrites_are_counted(rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rig.model.guard_says = True
    batch(tmp_path)
    out = capsys.readouterr().out
    count = int(re.search(r"wolf-chat rewrites: (\d+)", out).group(1))  # type: ignore[union-attr]
    assert count > 0
    assert count == sum(REWRITE in r.messages[1]["content"] for r in rig.model.calls)


def test_the_reasons_answers_were_turned_down_are_grouped(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = {"bid": 1, "message": "hi", "intent": "ask", "target": "Nobody", "note": "n",
           "beliefs": [], "cites": []}  # fmt: skip
    rig.model.raw["WireBid"] = json.dumps(bad)
    batch(tmp_path)
    out = capsys.readouterr().out
    assert re.search(r"rejected for: .*another living player.* x\d+", out)
    assert saved(tmp_path)[0].model == "gpt-4.1-nano"  # the log names the model
