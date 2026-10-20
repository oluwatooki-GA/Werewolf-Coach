"""The fact-check with a pretend model: what it is shown, what it flags, and how it stops."""

import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from test_derive import VILLAGER, WOLF_A, WOLF_B, base_log
from test_tagger import MODEL, talk

from werewolf import runtime
from werewolf.cli import main
from werewolf.engine.events import Death, Listening, VoteCast, WolfChat
from werewolf.engine.log import GameLog
from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import Ledger
from werewolf.llm.types import Completion, Request
from werewolf.tagger.grounding import GroundStopped, check_game, public_log

D = Decimal


class FakeGroundModel:
    def __init__(self) -> None:
        self.calls: list[Request] = []
        self.by_line: dict[str, str] = {}
        self.raw: str | None = None

    def provider(self, model: str) -> str:
        return "openai"

    def estimate(self, request: Request) -> Decimal:
        return D("0.000001")

    async def call(self, request: Request) -> Completion:
        self.calls.append(request)
        line = re.search(r"Message to check:\n\[(R\d+-\d+)\]", request.messages[1]["content"])
        assert line
        text = self.raw or json.dumps({"unsupported": self.by_line.get(line.group(1), "")})
        return Completion(
            model=request.model, text=text, prompt_tokens=100, completion_tokens=10,
            cost=D("0.000002"),
        )  # fmt: skip


class Rig:
    def __init__(self, tmp_path: Path, cap: str = "4.50") -> None:
        self.model = FakeGroundModel()
        self.ledger = Ledger(tmp_path / "ledger.json", {"openai": D(cap)})
        self.client = LLMClient(self.model, self.ledger, FileCache(tmp_path / "cache"))


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def game() -> GameLog:
    return base_log(
        talk((VILLAGER, "Hello all."), (WOLF_A, "Last time you were quiet."), (VILLAGER, "Why?"))
    )


def test_a_flagged_claim_is_reported_by_line_and_clean_messages_are_not(rig: Rig) -> None:
    rig.model.by_line["R1-2"] = "Last time you were quiet"
    run = asyncio.run(check_game(game(), rig.client, MODEL))
    assert run.checked == 3 and run.flagged == {"R1-2": "Last time you were quiet"}
    assert len(rig.model.calls) == 3


def test_the_word_none_is_not_a_claim(rig: Rig) -> None:
    rig.model.by_line["R1-1"] = "none"
    assert asyncio.run(check_game(game(), rig.client, MODEL)).flagged == {}


def test_the_checker_sees_only_the_public_log_up_to_the_message(rig: Rig) -> None:
    log = game()
    events = [
        WolfChat(round=1, speaker=WOLF_A, text="SECRET-WOLFCHAT", audience=(WOLF_A, WOLF_B)),
        Death(round=1, player=VILLAGER),
        Listening(round=1, player=WOLF_B),
        *talk((WOLF_A, "first"), (WOLF_B, "second")),
        VoteCast(round=1, voter=WOLF_A, target=WOLF_B, reason="odd"),
    ]
    log = log.model_copy(update={"events": events})
    asyncio.run(check_game(log, rig.client, MODEL))
    for request in rig.model.calls:
        text = " ".join(m["content"] for m in request.messages)
        assert "SECRET-WOLFCHAT" not in text and "Werewolf" not in request.messages[1]["content"]
    second = next(
        r
        for r in rig.model.calls
        if "[R1-2]" in r.messages[1]["content"].split("Message to check:")[1]
    )
    body = second.messages[1]["content"].split("Message to check:")[0]
    assert "[R1-1] " in body and "was killed in the night" in body and "stayed quiet" in body
    assert "second" not in body and "voted" not in body  # later events are not shown


def test_public_log_stops_before_the_message(rig: Rig) -> None:
    log = game()
    speech = [e for e in log.events if e.kind == "speech"][1]
    text = public_log(log, speech)
    assert "Hello all." in text and "Last time" not in text


def test_a_second_run_is_all_cache_hits(rig: Rig) -> None:
    asyncio.run(check_game(game(), rig.client, MODEL))
    again = asyncio.run(check_game(game(), rig.client, MODEL))
    assert len(rig.model.calls) == 3 and again.cache_hits == 3 and again.cost == 0


def test_an_unreadable_answer_is_counted_as_not_checked(rig: Rig) -> None:
    rig.model.raw = "not json"
    run = asyncio.run(check_game(game(), rig.client, MODEL))
    assert run.checked == 0 and len(run.failed) == 3


def test_a_spending_cap_stops_the_run_before_any_call(tmp_path: Path) -> None:
    rig = Rig(tmp_path, cap="0")
    with pytest.raises(GroundStopped):
        asyncio.run(check_game(game(), rig.client, MODEL))
    assert rig.model.calls == []


def test_the_command_prints_flagged_claims_and_the_rate(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_build(model: str, max_spend: object, **kw: object) -> LLMClient:
        return rig.client

    monkeypatch.setattr(runtime, "build_client", fake_build)
    rig.model.by_line["R1-2"] = "Last time you were quiet"
    path = tmp_path / "1-a.json"
    path.write_bytes(game().to_json().encode("utf-8"))
    assert main(["ground", str(path), "--model", MODEL, "--max-spend", "1.00"]) == 0
    out = capsys.readouterr().out
    assert "3 messages checked, 1 with an unsupported claim" in out
    assert "R1-2" in out and "Last time you were quiet" in out
    assert "unsupported claims: 1 of 3 messages (33%)" in out
