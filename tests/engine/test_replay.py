import asyncio
import json

import pytest

from werewolf.agents.scripted import policy
from werewolf.engine.actions import Agent, Task
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replay, replays_exactly, to_log
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings, SpeakingMode
from werewolf.engine.views import PlayerView


def table(seed: int, **opts: bool) -> dict[str, Agent]:
    wolves = [p.name for p in new_game(seed).players if p.role is Role.WEREWOLF]
    return {p.name: policy(wolves, **opts) for p in new_game(seed).players}


def logged(
    seed: int = 1, settings: Settings | None = None, agents: dict[str, Agent] | None = None
) -> GameLog:
    agents = agents or table(seed)
    return to_log(asyncio.run(play_game(seed, settings, agents)))


class Flaky:
    """Wraps a player and spoils some answers: bad schema, bad JSON, a crash."""

    def __init__(self, inner: Agent) -> None:
        self._inner = inner
        self._asked: dict[str, int] = {}

    async def act(self, view: PlayerView, task: Task) -> object:
        n = self._asked[task.kind] = self._asked.get(task.kind, 0) + 1
        if task.kind == "vote" and n <= 2:
            return "this is not json"  # both attempts bad: falls back to abstaining
        if task.kind == "night_target" and n == 1:
            return {"target": 123}  # bad schema: one retry fixes it
        if task.kind == "wolf_chat" and n == 1:
            raise RuntimeError("model timed out")
        return await self._inner.act(view, task)


def flaky_table(seed: int = 1) -> dict[str, Agent]:
    return {name: Flaky(agent) for name, agent in table(seed).items()}


def test_the_log_holds_everything_needed_to_understand_the_game() -> None:
    log = logged()
    assert log.seed == 1
    assert log.settings == Settings()
    assert [p.name for p in log.players] == [p.name for p in new_game(1).players]
    assert {p.role for p in log.players} == set(Role)
    assert log.winner is Team.VILLAGE
    assert log.events and log.calls
    assert log.calls[0].responses  # the raw answers are kept


def test_the_log_counts_responses_rejections_and_clean_games() -> None:
    clean = logged().stats
    assert clean.rejected == 0 and clean.failed_calls == 0 and clean.clean
    assert clean.responses == sum(len(c.responses) for c in logged().calls)

    messy = logged(agents=flaky_table()).stats
    assert messy.rejected > 0 and messy.failed_calls > 0 and not messy.clean


def test_the_json_is_canonical() -> None:
    text = logged().to_json()
    assert text.endswith("\n") and "\r" not in text
    assert text.isascii()
    data = json.loads(text)
    assert text == json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def test_json_round_trips() -> None:
    log = logged()
    assert GameLog.from_json(log.to_json()) == log


def test_replay_reproduces_a_byte_identical_log() -> None:
    log = logged()
    assert replay(log).to_json() == log.to_json()
    assert replays_exactly(log)


@pytest.mark.parametrize("mode", list(SpeakingMode))
def test_replay_is_exact_in_every_speaking_mode(mode: SpeakingMode) -> None:
    assert replays_exactly(logged(settings=Settings(speaking_mode=mode)))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_replay_is_exact_across_seeds(seed: int) -> None:
    assert replays_exactly(logged(seed=seed))


def test_replay_is_exact_even_when_answers_were_retried_crashed_or_fell_back() -> None:
    log = logged(agents=flaky_table())
    errors = [e for c in log.calls for e in c.errors]
    assert any("timed out" in e for e in errors)  # a crash
    assert any(c.failed for c in log.calls)  # a fallback
    assert any(c.rejected == 1 and not c.failed for c in log.calls)  # a retry that worked
    assert replay(log).to_json() == log.to_json()


def test_a_changed_response_no_longer_replays_to_the_same_log() -> None:
    log = logged()
    tampered = log.model_copy(deep=True)
    vote = next(c for c in tampered.calls if c.task["kind"] == "vote" and c.responses)
    vote.responses[0] = {"target": None, "reason": "tampered"}
    assert not replays_exactly(tampered)


def test_a_changed_seed_no_longer_replays_to_the_same_log() -> None:
    log = logged()
    assert not replays_exactly(log.model_copy(update={"seed": 2}))


def test_different_seeds_make_different_logs() -> None:
    assert logged(seed=1).to_json() != logged(seed=2).to_json()


def test_a_replay_never_calls_a_model_or_the_original_agents() -> None:
    log = logged()
    # replay() takes only the log: there is no way to pass it agents.
    assert replay(log).events == log.events
