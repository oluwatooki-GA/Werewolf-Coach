"""Checking a challenger card: code checks first, then a cheap model, with up to two rewrites."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from coach_support import CoachFake, coach_client

from werewolf.coach.check import CheckOutcome, changes, code_problems, write_checked_card
from werewolf.coach.steps import Diagnosis
from werewolf.engine.roles import Role
from werewolf.strategies.cards import Card

WRITER, CHECKER = "claude-sonnet-5-5", "claude-haiku-5-5"
BASE = "Take the lead and accuse early."
INSTRUCTIONS = "Bid 1 on day 1. Wait for two messages, then accuse with a cited line."


def reply(extra: str = INSTRUCTIONS, *, keep: bool = True) -> str:
    """A card reply that keeps the champion's sentence and adds `extra` (or stands alone)."""
    return json.dumps(
        {
            "name": "wait a beat",
            "summary": "Wait.",
            "instructions": f"{BASE} {extra}" if keep else extra,
            "expected_moves": ["hedge"],
        }
    )


def verdict(ok: bool, *reasons: str) -> str:
    return json.dumps({"ok": ok, "reasons": list(reasons)})


def champion() -> Card:
    return Card(
        id="wolf.accuse_early", version=2, role=Role.WEREWOLF, source="s", summary="Lead.",
        instructions="Take the lead and accuse early.", expected_moves=("accuse_reasoned",),
    )  # fmt: skip


def run(
    tmp_path: Path, cards: list[str], checks: list[str], side: str = "wolf"
) -> tuple[CheckOutcome, CoachFake]:
    client, fake = coach_client(tmp_path)
    fake.replies["WireCard"] = cards
    fake.replies["WireCheck"] = checks
    diagnosis = Diagnosis(text="They accused too early.", evidence=["Game 1."])
    outcome = asyncio.run(
        write_checked_card(client, WRITER, CHECKER, side, 1, diagnosis, champion())
    )
    return outcome, fake


def test_a_card_that_passes_at_once_is_returned_with_one_attempt(tmp_path: Path) -> None:
    outcome, fake = run(tmp_path, [reply()], [verdict(True)])
    assert outcome.card is not None and outcome.attempts == 1 and outcome.reasons == []
    assert outcome.validity == 1
    assert len(fake.asked("WireCheck")) == 1


def test_a_card_that_fails_a_code_check_never_reaches_the_model_check(tmp_path: Path) -> None:
    named = reply("Ask Ada why she was quiet on day 1.")
    outcome, fake = run(tmp_path, [named, reply()], [verdict(True)])
    assert outcome.attempts == 2 and outcome.card is not None
    assert "names a player" in outcome.reasons[0][0]
    assert len(fake.asked("WireCheck")) == 1  # only the second card was checked by the model


def test_a_card_that_repeats_the_champion_fails(tmp_path: Path) -> None:
    same = reply("Take the lead  and accuse early.", keep=False)  # same words, different spacing
    outcome, _ = run(tmp_path, [same, reply()], [verdict(True)])
    assert outcome.attempts == 2 and "same instructions as the champion" in outcome.reasons[0][0]


def test_a_card_the_model_rejects_is_rewritten_with_the_reasons(tmp_path: Path) -> None:
    reasons = "it relies on knowing who the wolves are"
    outcome, fake = run(
        tmp_path, [reply(), reply("Bid 2 on day 1.")], [verdict(False, reasons), verdict(True)]
    )
    assert outcome.attempts == 2 and outcome.card is not None
    assert outcome.card.instructions == f"{BASE} Bid 2 on day 1."
    assert outcome.reasons == [[reasons]]
    first, second = fake.asked("WireCard")
    assert reasons not in first.messages[1]["content"]
    assert reasons in second.messages[1]["content"]
    assert outcome.validity == 0.5


def test_three_failures_give_no_card_and_all_three_sets_of_reasons(tmp_path: Path) -> None:
    cards = [reply(f"Bid {n} on day 1.") for n in (1, 2, 3)]
    outcome, fake = run(tmp_path, cards, [verdict(False, "bad one"), verdict(False, "bad two")])
    assert outcome.card is None and outcome.attempts == 3
    assert len(outcome.reasons) == 3 and outcome.validity == 0
    assert outcome.reasons[0] == ["bad one"] and outcome.reasons[2] == ["bad two"]
    assert len(fake.asked("WireCard")) == 3  # never a fourth try


def test_the_model_check_sees_only_the_role_and_the_card(tmp_path: Path) -> None:
    _, fake = run(tmp_path, [reply()], [verdict(True)])
    (request,) = fake.asked("WireCheck")
    text = " ".join(m["content"] for m in request.messages)
    assert INSTRUCTIONS in text and "werewolf" in text.lower()
    assert "They accused too early." not in text and "Game 1." not in text
    assert request.model == CHECKER and request.temperature == 0


def test_every_call_is_paid_for_and_counted(tmp_path: Path) -> None:
    outcome, fake = run(tmp_path, [reply(), reply("Bid 2.")], [verdict(False, "x"), verdict(True)])
    assert outcome.cost == Decimal("0.01") * len(fake.requests) == Decimal("0.04")


def test_a_card_that_keeps_nothing_of_the_champion_is_sent_back(tmp_path: Path) -> None:
    fresh = reply("Stay quiet on day 1 and vote with the majority.", keep=False)
    outcome, _ = run(tmp_path, [fresh, reply()], [verdict(True)])
    assert (
        outcome.attempts == 2 and "keeps 0 of the champion's 1 sentences" in outcome.reasons[0][0]
    )
    assert outcome.card is not None and BASE in outcome.card.instructions
    assert outcome.card.parent == "wolf.accuse_early@2"


def test_the_changes_list_what_was_taken_out_and_what_was_put_in() -> None:
    base = champion()
    new = base.model_copy(
        update={"instructions": "Take the lead. Bid 2. Never accuse your partner."}
    )
    assert changes(base, new) == [
        "- Take the lead and accuse early.",
        "+ Take the lead.",
        "+ Bid 2.",
        "+ Never accuse your partner.",
    ]
    assert changes(base, base) == []


def test_a_card_must_keep_at_least_half_of_a_longer_base_word_for_word(tmp_path: Path) -> None:
    four = champion().model_copy(update={"instructions": "One a. Two b. Three c. Four d."})
    keeps_one = four.model_copy(update={"instructions": "One a. New x. New y. New z."})
    keeps_two = four.model_copy(update={"instructions": "One a. Two b. New x. New y."})
    assert (
        "keeps 1 of the champion's 4 sentences; keep at least 2"
        in code_problems(keeps_one, four)[0]
    )
    assert code_problems(keeps_two, four) == []
