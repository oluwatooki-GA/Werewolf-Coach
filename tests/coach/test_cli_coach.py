"""The coach commands, with fake models behind the real client and the real command line."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from coach_support import (
    WOLF_A,
    CoachFake,
    both_client,
    make_log,
    removed,
    speech,
    tag,
    tags_for,
)

from werewolf import runtime
from werewolf.cli import main
from werewolf.coach import graph
from werewolf.coach.arena import Arm
from werewolf.coach.history import load_history
from werewolf.engine.roles import Team
from werewolf.llm.client import LLMClient
from werewolf.tagger.tags import save_tags

REPO = Path(__file__).resolve().parents[2]
CHAMPION = "wolf.accuse_early"
DIAGNOSIS = json.dumps({"diagnosis": "They accused too early.", "evidence": ["Game 1."]})
OK = json.dumps({"ok": True, "reasons": []})


def card(words: str) -> str:
    return json.dumps(
        {
            "name": words,
            "summary": "Wait.",
            "instructions": f"Take the lead and speak often: bid 2 or 3 on most turns. {words}",
            "expected_moves": ["accuse_reasoned"],
        }
    )


class Rig:
    """The fake client the commands get, and what they asked it for."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.client, self.coach, self.players = both_client(tmp_path / "rig")
        self.coach.replies.update(
            {
                "WireDiagnosis": [DIAGNOSIS],
                "WireCard": [card("Bid 1 on day 1."), card("Bid 2 on day 1.")],
                "WireCheck": [OK],
            }
        )
        self.built: list[tuple[str, object, object]] = []
        self.played: list[str] = []
        rig = self

        def fake_build(model: str, max_spend: object, **kw: object) -> LLMClient:
            rig.built.append((model, max_spend, kw.get("flag")))
            return rig.client

        monkeypatch.setattr(runtime, "build_client", fake_build)

    def calls(self) -> int:
        return len(self.coach.requests) + len(self.players.calls)  # type: ignore[attr-defined]

    def arms(self, monkeypatch: pytest.MonkeyPatch, *, stop: bool = False) -> None:
        """Games with set results (equal wins, so the champion stays) instead of real ones."""

        async def fake_play(
            client: LLMClient, model: str, side: str, card_id: str, seeds: list[int], **_: Any
        ) -> Arm:
            self.played.append(card_id)
            stopped = "spending cap" if stop else None
            return Arm(
                card_id, side, list(seeds), 1, len(seeds), True, Decimal("1"), stopped=stopped
            )

        monkeypatch.setattr(graph, "play_arm", fake_play)


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    shutil.copytree(REPO / "cards", tmp_path / "cards", ignore=shutil.ignore_patterns("coach"))
    monkeypatch.chdir(tmp_path)
    return Rig(tmp_path, monkeypatch)


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    """A folder with one tagged game the wolves lost with the starting champion."""
    folder = tmp_path / "e1"
    folder.mkdir()
    events = [speech(1, WOLF_A, "Odd."), removed(1, WOLF_A)]
    log = make_log(Team.VILLAGE, events, rounds=2, card=f"{CHAMPION}@2")
    path = folder / "1-abc.json"
    path.write_bytes(log.to_json().encode("utf-8"))
    save_tags(path, tags_for(tag("R1-1", WOLF_A, 1, "accuse_reasoned")))
    return folder


def coach(*extra: str, evidence: Path, side: str = "wolf", generations: int = 1) -> int:
    return main(
        [
            "coach",
            "run",
            "--side",
            side,
            "--generations",
            str(generations),
            "--games",
            "2",
            "--evidence",
            str(evidence),
            "--max-spend-players",
            "1",
            "--max-spend-coach",
            "1",
            *extra,
        ]  # fmt: skip
    )


def test_a_run_plays_the_generations_and_saves_each(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.arms(monkeypatch)
    assert coach(evidence=evidence, generations=2) == 0
    history = load_history("wolf", Path("data/coach"))
    assert [g.number for g in history] == [1, 2]
    assert history[1].champion_before == history[0].champion_after
    out = capsys.readouterr().out
    assert "generation 1" in out and "generation 2" in out and "Champion now" in out


def test_each_generation_tests_on_new_seeds(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.arms(monkeypatch)
    coach("--first-seed", "50", evidence=evidence, generations=2)
    history = load_history("wolf", Path("data/coach"))
    assert history[0].champion_arm and history[1].champion_arm
    assert history[0].champion_arm.seeds == [50, 51]
    assert history[1].champion_arm.seeds == [52, 53]  # nothing is tested twice


def test_a_second_run_resumes_after_the_last_finished_generation(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.arms(monkeypatch)
    assert coach(evidence=evidence, generations=1) == 0
    first = load_history("wolf", Path("data/coach"))[0]
    assert len(rig.played) == 2  # the champion and the challenger, once
    assert coach(evidence=evidence, generations=2) == 0
    history = load_history("wolf", Path("data/coach"))
    assert [g.number for g in history] == [1, 2] and history[0] == first
    assert len(rig.played) == 4  # generation 1 was not played again


def test_a_cap_stops_the_run_with_a_message_and_a_rerun_finishes_it(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.arms(monkeypatch, stop=True)
    assert coach(evidence=evidence) == 1
    out = capsys.readouterr().out
    assert "STOPPED" in out and "spending cap" in out and "run again to resume" in out
    assert load_history("wolf", Path("data/coach")) == []
    rig.arms(monkeypatch)
    assert coach(evidence=evidence) == 0
    assert len(load_history("wolf", Path("data/coach"))) == 1


def test_show_prints_the_family_tree(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["coach", "show", "--side", "wolf"]) == 0
    assert "no generations yet" in capsys.readouterr().out
    rig.arms(monkeypatch)
    coach(evidence=evidence)
    capsys.readouterr()
    assert main(["coach", "show", "--side", "wolf"]) == 0
    out = capsys.readouterr().out
    assert "Generation 1" in out and "diagnosis: They accused too early." in out


def test_the_two_limits_go_to_the_two_clients(
    rig: Rig, evidence: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.arms(monkeypatch)
    assert coach("--player-model", "gpt-4.1-nano", evidence=evidence) == 0
    assert rig.built == [
        ("claude-sonnet-5-5", Decimal("1"), "--max-spend-coach"),
        ("gpt-4.1-nano", Decimal("1"), "--max-spend-players"),
    ]


def test_a_paid_model_without_its_limit_is_refused_before_any_call(
    tmp_path: Path,
    evidence: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shutil.copytree(REPO / "cards", tmp_path / "cards", ignore=shutil.ignore_patterns("coach"))
    monkeypatch.chdir(tmp_path)
    code = main(["coach", "run", "--side", "wolf", "--evidence", str(evidence)])
    assert code == 2
    assert "--max-spend-coach" in capsys.readouterr().err
    assert not Path("data/coach").exists()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--champion", "wolf.nope"], "no card"),
        (["--champion", "villager.quiet_observer"], "needs another"),
        (["--evidence", "nowhere"], "no games found in: nowhere"),
    ],
)
def test_a_bad_champion_or_missing_evidence_stops_before_any_call(
    rig: Rig, evidence: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    args = ["--evidence", str(evidence), *extra]  # a later --evidence replaces the first
    code = main(
        [
            "coach",
            "run",
            "--side",
            "wolf",
            "--max-spend-players",
            "1",
            "--max-spend-coach",
            "1",
            *args,
        ]
    )
    assert code == 2 and message in capsys.readouterr().err
    assert rig.calls() == 0 and rig.built == []


def test_a_bad_side_is_refused_by_the_parser(rig: Rig, evidence: Path) -> None:
    with pytest.raises(SystemExit):
        main(["coach", "run", "--side", "seer", "--evidence", str(evidence)])
    assert rig.calls() == 0


def test_one_real_generation_with_fake_players_runs_from_the_command(
    rig: Rig, evidence: Path
) -> None:
    code = coach("--parallel", "2", evidence=evidence)
    history = load_history("wolf", Path("data/coach"))
    assert code == 0 and len(history) == 1
    assert history[0].champion_arm and history[0].challenger_arm
    assert history[0].champion_arm.games == history[0].challenger_arm.games == 2
    assert isinstance(rig.coach, CoachFake) and len(rig.coach.requests) == 3
