import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from werewolf.agents.llm_agent import LLMAgent
from werewolf.engine.actions import Agent, FatalAgentError
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replays_exactly, to_log
from werewolf.engine.setup import new_game
from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import Ledger
from werewolf.llm.types import Completion, Request

D = Decimal
MODEL = "gpt-4.1-nano"


def player_of(request: Request) -> str:
    match = re.search(r"You are (\w+), a player", request.messages[0]["content"])
    assert match
    return match.group(1)


def options_of(request: Request) -> list[str]:
    match = re.search(r"Options: ([^.]*)\.", request.messages[1]["content"])
    assert match
    return [name.strip() for name in match.group(1).split(",")]


def is_wolf(request: Request) -> bool:
    return "the Werewolf." in request.messages[0]["content"]


class FakeModel:
    """A pretend model: answers every schema with valid wire JSON. Counts and records calls."""

    def __init__(self) -> None:
        self.calls: list[Request] = []
        self.fail_with: Exception | None = None
        self.raw: dict[str, str] = {}  # schema title -> exact text to return instead
        self.truncate = False
        self.beliefs_for: dict[str, list[dict[str, Any]]] = {}

    def provider(self, model: str) -> str:
        return "openai"

    def estimate(self, request: Request) -> Decimal:
        return D("0.000001")

    async def call(self, request: Request) -> Completion:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        assert request.schema_ is not None
        title = request.schema_["title"]
        text = self.raw.get(title) or json.dumps(self.answer(title, request))
        prompt = sum(len(m["content"]) for m in request.messages) // 4
        return Completion(
            model=request.model,
            text=text,
            prompt_tokens=prompt,
            completion_tokens=20,
            cached_tokens=prompt // 2,
            cost=D("0.000002"),
            latency_s=0.1,
            truncated=self.truncate,
        )

    def answer(self, title: str, request: Request) -> dict[str, Any]:
        me = player_of(request)
        if title == "WireChat":
            return {"text": "let us hunt", "note": "n"}
        if title == "WireTarget":
            purpose = request.messages[1]["content"]
            pick = (
                options_of(request)[0] if ("wolves kill" in purpose or "check" in purpose) else ""
            )
            return {"target": pick, "note": "n"}
        if title == "WireBid":
            return {
                "bid": 0, "message": "", "intent": "none", "target": "", "note": "n",
                "beliefs": self.beliefs_for.get(me, []),
            }  # fmt: skip
        assert title == "WireVote"
        pick = "" if is_wolf(request) else options_of(request)[0]
        return {"target": pick, "reason": "r", "note": "n", "beliefs": []}


class Rig:
    def __init__(self, tmp_path: Path, cap: str = "4.50") -> None:
        self.model = FakeModel()
        self.ledger = Ledger(tmp_path / "ledger.json", {"openai": D(cap)})
        self.client = LLMClient(self.model, self.ledger, FileCache(tmp_path / "cache"))
        self.prompts: list[tuple[str, list[dict[str, str]]]] = []

    def agents(self, seed: int = 1, salt: str = "", game_id: str = "g1") -> dict[str, Agent]:
        return {
            p.name: LLMAgent(
                p.name,
                self.client,
                MODEL,
                cache_salt=salt,
                game_id=game_id,
                on_prompt=lambda name, messages: self.prompts.append((name, messages)),
            )
            for p in new_game(seed).players
        }

    def play(self, seed: int = 1, salt: str = "", game_id: str = "g1") -> GameLog:
        agents = self.agents(seed, salt, game_id)
        return to_log(asyncio.run(play_game(seed, None, agents)))


def test_a_whole_game_plays_to_a_winner_with_model_players(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    log = rig.play()
    assert log.winner is not None
    assert log.stats.clean and log.stats.rejected == 0
    assert all(call.usage and call.usage[0] is not None for call in log.calls)


def test_the_log_totals_match_what_the_ledger_was_charged(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    log = rig.play()
    assert log.stats.cost == rig.ledger.spent("openai") > 0
    assert log.stats.cached_tokens > 0 and log.stats.prompt_tokens > log.stats.cached_tokens
    assert len(rig.model.calls) == len(log.calls)  # one model call per engine call, no retries


def test_each_living_player_makes_one_call_per_speaking_turn(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    log = rig.play()
    first_day = [c for c in log.calls if c.round == 1 and c.task["kind"] == "bid"]
    assert len(first_day) == 7  # everyone bid 0, so one turn; 7 alive after the first night kill


def test_a_beliefs_table_from_one_answer_appears_in_that_players_next_prompt(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)
    rig.model.beliefs_for["Cy"] = [{"player": "Bo", "suspicion": 0.8, "reason": "suspicious"}]
    rig.play()
    cy_vote = [
        m for name, m in rig.prompts if name == "Cy" and "Vote to remove" in m[1]["content"]
    ][0]
    assert "Bo: 0.8 (suspicious)" in cy_vote[1]["content"]
    earlier = [m for name, m in rig.prompts if name == "Cy"][0]
    assert "Bo: 0.8" not in earlier[1]["content"]


def test_the_cache_key_routes_one_players_calls_together(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.play(game_id="run-7")
    keys = {(player_of(r), r.prompt_cache_key) for r in rig.model.calls}
    assert all(key == f"run-7:{name}" for name, key in keys)


def test_every_prompt_is_reported_to_the_audit_callback(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    log = rig.play()
    assert len(rig.prompts) == len(rig.model.calls) == len(log.calls)
    assert all(len(messages) == 2 for _, messages in rig.prompts)


def test_a_cap_that_cannot_cover_a_call_stops_the_game_before_any_model_call(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, cap="0.0000005")
    with pytest.raises(FatalAgentError):
        rig.play()
    assert rig.model.calls == []


def test_a_cap_that_runs_out_mid_game_stops_it_instead_of_filling_it_with_fallbacks(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, cap="0.0000025")  # room for one call: it costs 0.000002
    with pytest.raises(FatalAgentError):
        rig.play()
    assert len(rig.model.calls) == 1
    assert rig.ledger.spent("openai") == D("0.000002")


def test_a_model_error_is_a_bad_answer_not_a_crash(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.model.fail_with = RuntimeError("rate limited")
    log = rig.play()
    assert log.stats.failed_calls > 0 and not log.stats.clean
    assert any("rate limited" in e for c in log.calls for e in c.errors)


def test_an_unreadable_answer_is_rejected_and_the_retry_carries_the_reason(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.model.raw["WireBid"] = '{"bid": "lots"}'
    log = rig.play()
    retries = [
        r for r in rig.model.calls if "Your last answer was rejected" in r.messages[1]["content"]
    ]
    assert retries
    assert any(c.rejected == 2 and c.failed for c in log.calls if c.task["kind"] == "bid")


def test_a_cut_off_answer_is_counted_and_rejected(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.model.truncate = True
    rig.model.raw["WireBid"] = '{"bid": 0, "message": "I think'
    log = rig.play()
    assert log.stats.truncated > 0
    assert log.stats.failed_calls > 0


def test_the_game_replays_exactly_with_no_model_at_all(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    log = rig.play()
    before = len(rig.model.calls)
    assert replays_exactly(log)
    assert len(rig.model.calls) == before


def test_the_same_seed_and_cards_with_a_new_salt_ask_the_model_again(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    first = rig.play(salt="run-1")
    calls_after_first = len(rig.model.calls)
    spent_after_first = rig.ledger.spent("openai")
    rig.play(salt="run-2")
    assert len(rig.model.calls) == 2 * calls_after_first
    assert rig.ledger.spent("openai") == 2 * spent_after_first
    assert first.stats.cost > 0


def test_the_same_salt_replays_a_game_from_the_cache_for_free(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    first = rig.play(salt="shared")
    calls, spent = len(rig.model.calls), rig.ledger.spent("openai")
    again = rig.play(salt="shared")
    assert len(rig.model.calls) == calls and rig.ledger.spent("openai") == spent
    assert again.events == first.events
    assert again.stats.cost == D("0")
    assert all(u.cache_hit for c in again.calls for u in c.usage if u is not None)
