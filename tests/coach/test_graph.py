"""One whole coach generation on fake models: read, diagnose, write, check, test, decide, record."""

import asyncio
import json
import re
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from coach_support import WOLF_A, Game, both_client, make_log, removed, speech, tag, tags_for

from werewolf.coach import graph
from werewolf.coach.arena import Arm
from werewolf.coach.history import Generation, family_tree, load_history
from werewolf.coach.steps import CoachStopped
from werewolf.engine.roles import Team
from werewolf.engine.state import Settings
from werewolf.llm.client import LLMClient

REPO = Path(__file__).resolve().parents[2]
CHAMPION = "wolf.accuse_early"
SEEDS = list(range(10))
DIAGNOSIS = json.dumps({"diagnosis": "They accused too early.", "evidence": ["Game 1: out in R1."]})
CARD = json.dumps(
    {
        "name": "wait a beat",
        "summary": "Wait.",
        "instructions": (
            "Take the lead and speak often: bid 2 or 3 on most turns. "
            "As soon as someone has said or voted something, accuse one player who is not your "
            "partner and back it with a reason from the log. "
            "Press again in later turns and call for a vote on them. "
            "Wait for two messages first."
        ),
        "expected_moves": ["accuse_reasoned"],
    }
)
OK = json.dumps({"ok": True, "reasons": []})
NOT_OK = json.dumps({"ok": False, "reasons": ["relies on knowing who the wolves are"]})


@pytest.fixture(autouse=True)
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A private copy of the starter cards, so coach cards are written there, not in the repo."""
    shutil.copytree(REPO / "cards", tmp_path / "cards", ignore=shutil.ignore_patterns("coach"))
    monkeypatch.chdir(tmp_path)


def lost_games() -> list[Game]:
    events = [speech(1, WOLF_A, "Odd."), removed(1, WOLF_A)]
    log = make_log(Team.VILLAGE, events, rounds=2, card=f"{CHAMPION}@2")
    return [(log, tags_for(tag("R1-1", WOLF_A, 1, "accuse_reasoned")))]


def coach_replies(fake: Any, check: str = OK) -> None:
    fake.replies.update({"WireDiagnosis": [DIAGNOSIS], "WireCard": [CARD], "WireCheck": [check]})


def fake_arms(monkeypatch: pytest.MonkeyPatch, champion: int, challenger: int) -> list[str]:
    """Replace the games with set results; returns the card ids that were played."""
    played: list[str] = []

    async def fake_play(
        client: LLMClient, model: str, side: str, card_id: str, seeds: list[int], **_: Any
    ) -> Arm:
        played.append(card_id)
        wins = champion if card_id == CHAMPION else challenger
        return Arm(card_id, side, list(seeds), wins, len(seeds), True, Decimal("1.5"))

    monkeypatch.setattr(graph, "play_arm", fake_play)
    return played


def generate(client: LLMClient, tmp_path: Path, number: int = 1) -> Generation:
    return asyncio.run(
        graph.run_generation(
            client, side="wolf", number=number, champion=CHAMPION, games=lost_games(),
            seeds=SEEDS, player_model="gpt-4.1-nano", coach_model="claude-sonnet-5-5",
            check_model="claude-haiku-5-5", settings=Settings(), data_dir=tmp_path / "games",
            root=tmp_path / "coach",
        )
    )  # fmt: skip


def test_a_challenger_that_clearly_wins_becomes_the_champion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)
    played = fake_arms(monkeypatch, champion=3, challenger=8)
    gen = generate(client, tmp_path)
    assert gen.promote and gen.champion_after == "wolf.wait_a_beat@1"
    assert gen.champion_before == f"{CHAMPION}@2" and "clear win" in gen.decision
    assert sorted(played) == sorted([CHAMPION, "wolf.wait_a_beat"])
    assert (tmp_path / "cards" / "coach" / "wolf.wait_a_beat.yaml").exists()
    assert load_history("wolf", tmp_path / "coach") == [gen]


def test_a_challenger_that_does_not_clearly_win_leaves_the_champion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)
    fake_arms(monkeypatch, champion=5, challenger=7)
    gen = generate(client, tmp_path)
    assert not gen.promote and gen.champion_after == gen.champion_before
    assert gen.challenger_card == "wolf.wait_a_beat@1" and "not clear yet" in gen.decision


def test_a_card_that_never_passes_its_checks_plays_no_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach, check=NOT_OK)
    played = fake_arms(monkeypatch, 5, 9)
    gen = generate(client, tmp_path)
    assert played == [] and gen.challenger_card is None and not gen.promote
    assert gen.champion_arm is None and gen.challenger_arm is None
    assert gen.check.attempts == 3 and not gen.check.passed and len(gen.check.reasons) == 3
    assert "none was played" in gen.decision
    assert gen.champion_after == gen.champion_before
    assert not list((tmp_path / "cards").glob("coach/*"))  # no card was written


def test_cost_is_the_coach_calls_plus_both_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)
    fake_arms(monkeypatch, 3, 8)
    gen = generate(client, tmp_path)
    assert len(coach.requests) == 3  # diagnose, write, check
    assert gen.coach_cost == Decimal("0.03") and gen.player_cost == Decimal("3.0")
    assert gen.cost == Decimal("3.03")


def test_a_run_stopped_in_the_games_saves_nothing_and_a_rerun_skips_the_paid_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)

    async def stopped(
        client: LLMClient, model: str, side: str, card_id: str, seeds: list[int], **_: Any
    ) -> Arm:
        return Arm(card_id, side, list(seeds), 0, 0, False, Decimal("0"), stopped="spending cap")

    monkeypatch.setattr(graph, "play_arm", stopped)
    with pytest.raises(CoachStopped, match="spending cap"):
        generate(client, tmp_path)
    assert load_history("wolf", tmp_path / "coach") == []
    paid = len(coach.requests)

    played = fake_arms(monkeypatch, 3, 8)
    gen = generate(client, tmp_path)
    assert len(coach.requests) == paid  # the model cache served the diagnosis, card and check
    assert gen.promote and len(played) == 2

    again = generate(client, tmp_path)  # a finished generation is never played twice
    assert again == gen and len(played) == 2


def test_a_generation_cannot_skip_ahead(tmp_path: Path) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)
    with pytest.raises(ValueError, match="cannot run"):
        generate(client, tmp_path, number=2)
    assert coach.requests == []


def test_a_whole_generation_with_fake_players_plays_both_arms_on_the_same_seeds(
    tmp_path: Path,
) -> None:
    client, coach, players = both_client(tmp_path / "rig")
    coach_replies(coach)
    gen = asyncio.run(
        graph.run_generation(
            client, side="wolf", number=1, champion=CHAMPION, games=lost_games(), seeds=[1, 2],
            player_model="gpt-4.1-nano", coach_model="claude-sonnet-5-5",
            check_model="claude-haiku-5-5", settings=Settings(summarize_rounds=True),
            data_dir=tmp_path / "games", root=tmp_path / "coach", parallel=2,
        )
    )  # fmt: skip
    assert gen.champion_arm and gen.challenger_arm
    assert gen.champion_arm.seeds == gen.challenger_arm.seeds == [1, 2]
    assert gen.champion_arm.games == gen.challenger_arm.games == 2
    assert gen.player_cost > 0 and gen.cost == gen.coach_cost + gen.player_cost
    assert players.calls  # type: ignore[attr-defined]


def test_only_the_graph_module_imports_langgraph() -> None:
    pattern = re.compile(r"^\s*(import|from)\s+langgraph", re.MULTILINE)
    users = {
        path.name
        for path in (REPO / "src" / "werewolf").rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    }
    assert users == {"graph.py"}


def test_the_record_keeps_the_parent_and_what_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, coach, _ = both_client(tmp_path / "rig")
    coach_replies(coach)
    fake_arms(monkeypatch, 5, 5)
    gen = generate(client, tmp_path)
    assert "+ Wait for two messages first." in gen.changes
    assert not any("Take the lead and speak often" in change for change in gen.changes)  # kept
    assert "- Always give a reason." in gen.changes  # dropped, as the card says nothing of it
    text = (tmp_path / "cards" / "coach" / "wolf.wait_a_beat.yaml").read_text(encoding="utf-8")
    assert "parent: wolf.accuse_early@2" in text
    assert "+ Wait for two messages first." in family_tree("wolf", tmp_path / "coach")
