"""The slip guard: a wolf's public message is checked against its own wolf chat before posting."""

from decimal import Decimal
from pathlib import Path

import pytest
from test_llm_agent import Rig, is_wolf

from werewolf.agents.leakguard import REWRITE, reveals
from werewolf.engine.log import GameLog
from werewolf.llm.types import Request

D = Decimal


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    rig = Rig(tmp_path)
    rig.model.talk = True  # every player always asks for the floor with a new message
    return rig


def guard_calls(rig: Rig) -> list[Request]:
    return [r for r in rig.model.calls if r.schema_ and r.schema_["title"] == "WireGuard"]


def bid_calls(rig: Rig, wolf: bool) -> list[Request]:
    return [
        r for r in rig.model.calls
        if r.schema_ and r.schema_["title"] == "WireBid" and is_wolf(r) == wolf
    ]  # fmt: skip


def test_only_wolves_with_a_message_and_a_wolf_chat_are_checked(rig: Rig) -> None:
    rig.play()
    guards = guard_calls(rig)
    assert guards and len(guards) == len(bid_calls(rig, wolf=True))
    for call in guards:
        text = call.messages[1]["content"]
        assert "Private wolf chat:" in text and "Public message to check:\nI have question" in text


def test_no_guard_call_for_a_quiet_wolf_or_for_villagers(tmp_path: Path) -> None:
    rig = Rig(tmp_path)  # the default fake bids 0 with an empty message
    rig.play()
    assert guard_calls(rig) == []


def test_a_revealing_message_is_sent_back_once_with_the_reason(rig: Rig) -> None:
    rig.model.guard_says = True
    log = rig.play()
    wolf_asks = bid_calls(rig, wolf=True)
    guards = guard_calls(rig)
    assert len(wolf_asks) == 2 * len(guards)  # each checked answer was asked for again, once
    assert sum(REWRITE in r.messages[1]["content"] for r in wolf_asks) == len(guards)
    assert not any(REWRITE in r.messages[1]["content"] for r in bid_calls(rig, wolf=False))
    assert isinstance(log, GameLog)


def test_the_logged_cost_of_a_checked_answer_includes_all_its_calls(rig: Rig) -> None:
    rig.model.guard_says = True
    log = rig.play()
    wolves = {p.name for p in log.players if p.role.value == "Werewolf"}
    call = next(
        c for c in log.calls
        if c.player in wolves and c.task["kind"] == "bid" and c.usage and c.usage[0]
    )  # fmt: skip
    first = call.usage[0]
    assert first is not None and first.cost == D("0.000006")  # answer, guard, answer again


def test_an_answer_the_guard_clears_is_posted_as_it_was(rig: Rig) -> None:
    rig.model.guard_says = False
    rig.play()
    assert not any(REWRITE in r.messages[1]["content"] for r in rig.model.calls if r.messages)


def test_an_unreadable_guard_answer_is_not_a_verdict(rig: Rig) -> None:
    assert reveals('{"reveals": true}') is True
    assert reveals('{"reveals": false}') is False
    for junk in ("not json", "{}", '{"reveals": "maybe"}', '{"reveals": true, "x": 1}'):
        assert reveals(junk) is False


def test_a_failing_guard_call_does_not_cost_the_wolf_its_turn(rig: Rig) -> None:
    rig.model.raw["WireGuard"] = "not json"
    log = rig.play()
    assert log.stats.failed_calls == 0
