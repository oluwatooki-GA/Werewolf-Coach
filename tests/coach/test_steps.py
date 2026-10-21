"""The coach's two steps, with a pretend model: diagnose a lost side, write a challenger."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from coach_support import CoachFake, coach_client

from werewolf.coach.evidence import Evidence
from werewolf.coach.steps import (
    CoachError,
    CoachStopped,
    Diagnosis,
    card_id,
    diagnose,
    write_challenger,
)
from werewolf.engine.roles import Role
from werewolf.strategies.cards import Card

MODEL = "claude-sonnet-5-5"
DIGEST = "Game 1: lost in round 2.\n  [R1-1] Wolf A (accuse_reasoned -> Villager 1) Odd silence."
GOOD_DIAGNOSIS = json.dumps(
    {
        "diagnosis": "The wolves accused at once and were voted out by round 2.",
        "evidence": ["Game 1, R1-1: Wolf A accused first and was removed in round 1."],
    }
)
GOOD_CARD = json.dumps(
    {
        "summary": "Wait for a second message.",
        "instructions": "Bid 1 on day 1. Wait for two messages, then accuse with a cited line.",
        "expected_moves": ["accuse_reasoned", "hedge"],
    }
)


def evidence() -> Evidence:
    return Evidence("wolf", "wolf.accuse_early", games=18, lost=5, used=1, left_out=0, text=DIGEST)


def champion() -> Card:
    return Card(
        id="wolf.accuse_early", version=2, role=Role.WEREWOLF, source="s", summary="Lead.",
        instructions="Take the lead and accuse early.", expected_moves=("accuse_reasoned",),
    )  # fmt: skip


def run_diagnose(tmp_path: Path, replies: list[str]) -> tuple[Diagnosis, Decimal, CoachFake]:
    client, fake = coach_client(tmp_path)
    fake.replies["WireDiagnosis"] = replies
    diagnosis, cost = asyncio.run(diagnose(client, MODEL, evidence(), champion()))
    return diagnosis, cost, fake


def test_the_diagnosis_prompt_holds_the_digest_and_the_champion_card(tmp_path: Path) -> None:
    _, _, fake = run_diagnose(tmp_path, [GOOD_DIAGNOSIS])
    (request,) = fake.asked("WireDiagnosis")
    text = " ".join(m["content"] for m in request.messages)
    assert DIGEST in text and "Take the lead and accuse early." in text
    assert "the wolf side" in text


def test_a_good_diagnosis_is_returned_with_its_evidence_and_its_cost(tmp_path: Path) -> None:
    diagnosis, cost, _ = run_diagnose(tmp_path, [GOOD_DIAGNOSIS])
    assert diagnosis.text.startswith("The wolves accused at once")
    assert diagnosis.evidence == ["Game 1, R1-1: Wolf A accused first and was removed in round 1."]
    assert cost == Decimal("0.01")


def test_an_invalid_reply_is_asked_again_once_with_the_reason(tmp_path: Path) -> None:
    _, cost, fake = run_diagnose(tmp_path, ["not json", GOOD_DIAGNOSIS])
    first, second = fake.asked("WireDiagnosis")
    assert "not valid" not in first.messages[1]["content"]
    assert "not valid" in second.messages[1]["content"]
    assert cost == Decimal("0.02")  # both calls are paid for and counted


def test_two_invalid_replies_fail_with_a_clear_error_that_keeps_the_cost(tmp_path: Path) -> None:
    client, fake = coach_client(tmp_path)
    fake.replies["WireDiagnosis"] = ["nope", '{"diagnosis": 3}']
    with pytest.raises(CoachError, match="diagnosis") as error:
        asyncio.run(diagnose(client, MODEL, evidence(), champion()))
    assert error.value.cost == Decimal("0.02")


def test_there_is_nothing_to_diagnose_when_the_side_won_everything(tmp_path: Path) -> None:
    client, fake = coach_client(tmp_path)
    empty = Evidence("wolf", None, 3, 0, 0, 0, "There is nothing to learn from: it won all 3.")
    with pytest.raises(CoachError, match="nothing to"):
        asyncio.run(diagnose(client, MODEL, empty, champion()))
    assert fake.requests == []


def test_a_spending_cap_stops_the_step_with_a_clear_message(tmp_path: Path) -> None:
    client, fake = coach_client(tmp_path, cap="0")
    fake.replies["WireDiagnosis"] = [GOOD_DIAGNOSIS]
    with pytest.raises(CoachStopped):
        asyncio.run(diagnose(client, MODEL, evidence(), champion()))
    assert fake.requests == []


def diagnosis() -> Diagnosis:
    return Diagnosis(text="They accused too early.", evidence=["Game 1: removed in round 1."])


def run_write(
    tmp_path: Path, feedback: list[str] | None = None, replies: list[str] | None = None
) -> tuple[Card, Decimal, CoachFake]:
    client, fake = coach_client(tmp_path)
    fake.replies["WireCard"] = replies or [GOOD_CARD]
    card, cost = asyncio.run(
        write_challenger(client, MODEL, "wolf", 2, diagnosis(), champion(), feedback)
    )
    return card, cost, fake


def test_the_card_is_built_from_the_reply_but_its_identity_is_set_by_code(tmp_path: Path) -> None:
    card, _, _ = run_write(tmp_path)
    assert (card.id, card.version, card.role) == ("wolf.coach_g2", 1, Role.WEREWOLF)
    assert card.source == "the coach, generation 2, wolf side"
    assert card.instructions.startswith("Bid 1 on day 1")
    assert card.expected_moves == ("accuse_reasoned", "hedge")
    assert card_id("villager", 3, "r7") == "villager.coach_r7_g3"


def test_feedback_from_a_failed_check_appears_only_when_given(tmp_path: Path) -> None:
    _, _, fake = run_write(tmp_path)
    (plain,) = fake.asked("WireCard")
    assert "rejected" not in plain.messages[1]["content"]
    _, _, again = run_write(tmp_path / "again", feedback=["names a player (Ada)"])
    (with_feedback,) = again.asked("WireCard")
    assert "names a player (Ada)" in with_feedback.messages[1]["content"]


def test_the_prompt_lists_the_diagnosis_the_champion_and_the_allowed_moves(tmp_path: Path) -> None:
    _, _, fake = run_write(tmp_path)
    (request,) = fake.asked("WireCard")
    text = " ".join(m["content"] for m in request.messages)
    assert "They accused too early." in text and "Take the lead and accuse early." in text
    assert "accuse_reasoned" in text and "hedge" in text and "at most 80 words" in text


def test_an_unreadable_card_reply_is_asked_again_once_then_fails(tmp_path: Path) -> None:
    _, _, fake = run_write(tmp_path, replies=["???", GOOD_CARD])
    assert len(fake.asked("WireCard")) == 2
    client, broken = coach_client(tmp_path / "x")
    broken.replies["WireCard"] = ["???", '{"summary": "x"}']
    with pytest.raises(CoachError, match="card"):
        asyncio.run(write_challenger(client, MODEL, "wolf", 1, diagnosis(), champion(), None))
