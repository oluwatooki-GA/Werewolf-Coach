"""The tagger with a pretend model behind the real client, cache and ledger."""

import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from test_derive import SEER, VILLAGER, WOLF_A, WOLF_B, base_log

from werewolf.engine.events import Event, SeerResult, Speech, WolfChat
from werewolf.engine.log import GameLog
from werewolf.engine.roles import Role
from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import Ledger
from werewolf.llm.types import Completion, Request
from werewolf.tagger.tagger import TagStopped, tag_game, tag_schema

D = Decimal
MODEL = "gpt-4.1-nano"
PLAIN = {"move1": "probe", "move2": "none", "target": "", "claim_role": "none",
         "checked": "", "result": "none", "vote": ""}  # fmt: skip


class FakeTagModel:
    def __init__(self) -> None:
        self.calls: list[Request] = []
        self.by_line: dict[str, dict[str, str]] = {}
        self.fail_on: str | None = None
        self.truncate = False

    def provider(self, model: str) -> str:
        return "openai"

    def estimate(self, request: Request) -> Decimal:
        return D("0.000001")

    async def call(self, request: Request) -> Completion:
        self.calls.append(request)
        line = re.search(r"Message to label:\n\[(R\d+-\d+)\]", request.messages[1]["content"])
        assert line
        if self.fail_on == line.group(1):
            raise RuntimeError("boom")
        answer = self.by_line.get(line.group(1), PLAIN)
        return Completion(
            model=request.model,
            text=json.dumps(answer),
            prompt_tokens=100,
            completion_tokens=20,
            cost=D("0.000002"),
            truncated=self.truncate,
        )


class Rig:
    def __init__(self, tmp_path: Path, cap: str = "4.50", budget: Decimal | None = None) -> None:
        self.model = FakeTagModel()
        self.ledger = Ledger(tmp_path / "ledger.json", {"openai": D(cap)})
        self.client = LLMClient(
            self.model, self.ledger, FileCache(tmp_path / "cache"), run_budget=budget
        )


def talk(*lines: tuple[str, str]) -> list[Event]:
    return [Speech(round=1, speaker=who, text=text, paid=1) for who, text in lines]


def run(rig: Rig, log: GameLog, **kw: Any) -> Any:
    return asyncio.run(tag_game(log, rig.client, MODEL, **kw))


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def three() -> GameLog:
    return base_log(talk((VILLAGER, "I trust Bo."), (WOLF_A, "Why?"), (SEER, "Let us wait.")))


def test_every_public_message_is_tagged_once_with_its_line_number(rig: Rig) -> None:
    result = run(rig, three())
    assert [t.line for t in result.tags] == ["R1-1", "R1-2", "R1-3"]
    assert [t.speaker for t in result.tags] == [VILLAGER, WOLF_A, SEER]
    assert len(rig.model.calls) == 3 and result.untagged == {}


def test_the_prompt_holds_the_message_and_up_to_three_earlier_ones_and_nothing_secret(
    rig: Rig,
) -> None:
    events = [
        WolfChat(round=1, speaker=WOLF_A, text="SECRET-WOLFCHAT", audience=(WOLF_A, WOLF_B)),
        SeerResult(round=1, target=WOLF_A, role=Role.WEREWOLF, audience=(SEER,)),
        *talk(*[(VILLAGER, f"line number {n}") for n in range(1, 6)]),
    ]
    run(rig, base_log(events))
    sent = {r.messages[1]["content"] for r in rig.model.calls}
    fifth = next(s for s in sent if "[R1-5] " in s.split("Message to label:")[1])
    assert "line number 2" in fifth and "line number 1" not in fifth
    for request in rig.model.calls:
        text = " ".join(m["content"] for m in request.messages)
        assert "SECRET-WOLFCHAT" not in text and "audience" not in text
        assert not re.search(rf"{WOLF_A}\s*[:=(]\s*(Werewolf|wolf)", text, re.IGNORECASE)


def test_the_same_game_tagged_again_is_all_cache_hits_at_no_cost(rig: Rig) -> None:
    log = three()
    first = run(rig, log)
    again = run(rig, log)
    assert len(rig.model.calls) == 3 and again.cache_hits == 3 and again.cost == 0
    assert first.cost > 0 and again.tags == first.tags


def test_two_moves_a_target_and_a_claim_come_back_as_a_tag(rig: Rig) -> None:
    rig.model.by_line["R1-1"] = {
        "move1": "result_claim", "move2": "accuse_reasoned", "target": WOLF_A,
        "claim_role": "Seer", "checked": WOLF_A, "result": "wolf", "vote": "",
    }  # fmt: skip
    (tag, *_) = run(rig, three()).tags
    assert tag.moves == ("result_claim", "accuse_reasoned") and tag.target == WOLF_A
    assert tag.claimed is not None
    assert (tag.claimed.role, tag.claimed.checked, tag.claimed.result) == ("Seer", WOLF_A, "wolf")


@pytest.mark.parametrize(
    "change",
    [
        {"move1": "shout"},
        {"move2": "dance"},
        {"target": "Nobody"},
        {"move1": "role_claim"},  # a claim with no role
        {"move1": "result_claim", "claim_role": "Seer"},  # a result claim with no result
        {"move1": "result_claim", "claim_role": "Villager", "checked": "Bo", "result": "wolf"},
    ],
)
def test_an_unusable_answer_is_counted_and_not_stored_as_a_tag(
    rig: Rig, change: dict[str, str]
) -> None:
    rig.model.by_line["R1-1"] = {**PLAIN, **change}
    result = run(rig, three())
    assert "R1-1" in result.untagged and [t.line for t in result.tags] == ["R1-2", "R1-3"]


def test_claim_facts_on_a_non_claim_move_are_dropped(rig: Rig) -> None:
    rig.model.by_line["R1-1"] = {**PLAIN, "claim_role": "Seer", "checked": WOLF_A, "result": "wolf"}
    (tag, *_) = run(rig, three()).tags
    assert tag.claimed is None


def test_a_cut_off_answer_is_not_a_clean_tag(rig: Rig) -> None:
    rig.model.truncate = True
    result = run(rig, three())
    assert result.tags == [] and set(result.untagged) == {"R1-1", "R1-2", "R1-3"}


def test_an_ordinary_error_leaves_one_message_untagged_and_the_run_goes_on(rig: Rig) -> None:
    rig.model.fail_on = "R1-2"
    result = run(rig, three())
    assert "R1-2" in result.untagged and [t.line for t in result.tags] == ["R1-1", "R1-3"]


def test_a_spending_cap_stops_the_run_before_any_call_and_keeps_the_ledger(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, cap="0")
    with pytest.raises(TagStopped):
        run(rig, three())
    assert rig.model.calls == [] and rig.ledger.spent("openai") == 0


def test_a_run_budget_refuses_the_call_that_would_pass_it(tmp_path: Path) -> None:
    rig = Rig(tmp_path, budget=D("0.0000015"))  # room for one call's worst case, not two
    with pytest.raises(TagStopped) as stopped:
        run(rig, three())
    assert len(rig.model.calls) == 1 and len(stopped.value.run.tags) == 1
    assert rig.ledger.spent("openai") == D("0.000002")  # one call was paid, no second


def test_only_the_asked_for_lines_are_tagged(rig: Rig) -> None:
    result = run(rig, three(), only={"R1-3"})
    assert [t.line for t in result.tags] == ["R1-3"] and len(rig.model.calls) == 1


def test_the_schema_is_strict_and_lists_the_moves() -> None:
    schema = tag_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])
    assert "role_claim" in schema["properties"]["move1"]["enum"]
    assert "none" in schema["properties"]["move2"]["enum"]
