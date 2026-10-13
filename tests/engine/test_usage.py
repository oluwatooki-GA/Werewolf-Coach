import asyncio
import json
from decimal import Decimal

import pytest

from werewolf.agents.scripted import ScriptedAgent, from_queue, policy
from werewolf.engine.actions import (
    Agent,
    BidAction,
    BidTask,
    FatalAgentError,
    Reply,
    Task,
    Usage,
)
from werewolf.engine.asking import Asked, ask
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replay, replays_exactly, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.views import PlayerView, make_view

BID_TASK = BidTask(max_bid=3, max_chars=300)


def usage(n: int = 1, **kw: object) -> Usage:
    base = {
        "model": "gpt-4.1-nano",
        "prompt_tokens": 100 * n,
        "completion_tokens": 10 * n,
        "cached_tokens": 40 * n,
        "cost": Decimal("0.0000123") * n,
        "latency_s": 0.25 * n,
        "cache_hit": False,
    }
    return Usage.model_validate({**base, **kw})


def run_ask(agent: Agent, task: Task = BID_TASK) -> Asked:
    view = make_view(new_game(seed=1), "Ada")
    return asyncio.run(ask(agent, view, task, lambda action: None))


class Costed:
    """Wraps an agent so each answer comes back as a Reply with its own usage."""

    def __init__(self, inner: Agent, truncate_first: bool = False) -> None:
        self._inner, self._n, self._truncate_first = inner, 0, truncate_first

    async def act(self, view: PlayerView, task: Task) -> object:
        self._n += 1
        raw = await self._inner.act(view, task)
        text = raw.model_dump_json() if hasattr(raw, "model_dump_json") else raw
        if not isinstance(text, str):
            return raw
        truncated = self._truncate_first and self._n == 1
        return Reply(text=text, usage=usage(self._n % 3 + 1, truncated=truncated))


def costed_table(seed: int = 1, **kw: bool) -> dict[str, Agent]:
    wolves = [p.name for p in new_game(seed).players if p.role is Role.WEREWOLF]
    return {p.name: Costed(policy(wolves)) for p in new_game(seed).players}


def play(seed: int = 1, agents: dict[str, Agent] | None = None, run_id: str = "") -> GameLog:
    state = asyncio.run(play_game(seed, None, agents or costed_table(seed)))
    return to_log(state, run_id=run_id)


def test_ask_unwraps_a_reply_and_keeps_its_usage() -> None:
    u = usage()
    asked = run_ask(from_queue([Reply(text='{"bid": 2, "message": "hi"}', usage=u)]))
    assert asked.action == BidAction(bid=2, message="hi")
    assert asked.usage == [u]
    assert asked.responses == ['{"bid": 2, "message": "hi"}']


def test_a_plain_answer_has_no_usage() -> None:
    asked = run_ask(from_queue([BidAction(bid=1, message="x")]))
    assert asked.usage == [None]


def test_usage_lines_up_with_every_response_including_rejected_ones() -> None:
    first, second = usage(1), usage(2)
    asked = run_ask(
        from_queue(
            [
                Reply(text='{"bid": "lots"}', usage=first),
                Reply(text='{"bid": 1, "message": "ok"}', usage=second),
            ]
        )
    )
    assert asked.usage == [first, second]
    assert asked.rejected == 1


def test_a_crash_has_no_usage_but_the_retry_does() -> None:
    def respond(view: PlayerView, task: Task) -> object:
        if task.error is None:
            raise RuntimeError("model timed out")
        return Reply(text='{"bid": 1, "message": "ok"}', usage=usage())

    asked = run_ask(ScriptedAgent(respond))
    assert asked.usage == [None, usage()]


def test_a_fatal_error_is_not_retried_and_not_turned_into_a_bad_answer() -> None:
    calls: list[int] = []

    def respond(view: PlayerView, task: Task) -> object:
        calls.append(1)
        raise FatalAgentError("spending cap reached")

    with pytest.raises(FatalAgentError, match="spending cap"):
        run_ask(ScriptedAgent(respond))
    assert len(calls) == 1


def test_a_fatal_error_stops_a_whole_game() -> None:
    agents = costed_table()
    name = new_game(1).players[0].name

    def respond(view: PlayerView, task: Task) -> object:
        raise FatalAgentError("spending cap reached")

    agents[name] = ScriptedAgent(respond)
    with pytest.raises(FatalAgentError):
        asyncio.run(play_game(1, None, agents))


def test_the_log_keeps_usage_next_to_every_response() -> None:
    log = play()
    assert log.version == 2
    for call in log.calls:
        assert len(call.usage) == len(call.responses)
    assert any(u is not None for c in log.calls for u in c.usage)


def test_stats_total_the_tokens_and_the_cost_exactly() -> None:
    log = play()
    used = [u for c in log.calls for u in c.usage if u is not None]
    assert log.stats.prompt_tokens == sum(u.prompt_tokens for u in used)
    assert log.stats.completion_tokens == sum(u.completion_tokens for u in used)
    assert log.stats.cached_tokens == sum(u.cached_tokens for u in used)
    assert log.stats.cost == sum((u.cost for u in used), Decimal("0"))
    assert log.stats.cost == Decimal("0.0000123") * sum(
        (u.prompt_tokens // 100) for u in used
    )  # exact decimal arithmetic, no float drift


def test_truncated_answers_are_counted() -> None:
    wolves = [p.name for p in new_game(1).players if p.role is Role.WEREWOLF]
    agents = {p.name: Costed(policy(wolves), truncate_first=True) for p in new_game(1).players}
    log = play(agents=agents)
    assert log.stats.truncated == 8  # each player's first answer


def test_a_game_that_returns_replies_replays_byte_identically_with_usage() -> None:
    log = play()
    again = replay(log)
    assert again.to_json() == log.to_json()
    assert any(u is not None for c in again.calls for u in c.usage)


def test_the_run_id_is_kept_and_replays() -> None:
    log = play(run_id="run-abc123")
    assert log.run_id == "run-abc123"
    assert GameLog.from_json(log.to_json()).run_id == "run-abc123"
    assert replay(log).run_id == "run-abc123"
    assert replays_exactly(log)


def test_a_scripted_game_has_no_usage_and_zero_totals() -> None:
    wolves = [p.name for p in new_game(1).players if p.role is Role.WEREWOLF]
    agents = {p.name: policy(wolves) for p in new_game(1).players}
    stats = play(agents=agents).stats
    assert (stats.prompt_tokens, stats.completion_tokens, stats.cached_tokens) == (0, 0, 0)
    assert stats.cost == Decimal("0") and stats.truncated == 0


def test_a_version_1_log_without_usage_or_run_id_still_loads() -> None:
    wolves = [p.name for p in new_game(1).players if p.role is Role.WEREWOLF]
    agents = {p.name: policy(wolves) for p in new_game(1).players}
    data = json.loads(play(agents=agents).to_json())
    data["version"] = 1
    del data["run_id"]
    for call in data["calls"]:
        del call["usage"]
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens", "cost", "truncated"):
        del data["stats"][key]
    old = GameLog.model_validate(data)
    assert old.version == 1 and old.run_id == ""
    assert old.stats.cost == Decimal("0")
    assert replay(old).events == old.events
