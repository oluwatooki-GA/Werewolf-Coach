"""Scripted games with known outcomes. Seed 1 seats: Di Seer, Gus, Bo, Fay (wolf), Hal (wolf),
Ada Doctor, Eve, Cy. The scripts know the roles, so every result below can be worked out by hand."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from werewolf.agents.scripted import policy
from werewolf.engine.actions import Agent, BidAction, Task, VoteAction
from werewolf.engine.events import Death, Removal, Speech
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replays_exactly, to_log
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.views import PlayerView

SEED = 1
WOLVES = ["Fay", "Hal"]


def table(**opts: bool) -> dict[str, Agent]:
    return {p.name: policy(WOLVES, **opts) for p in new_game(SEED).players}


class Script:
    """Wraps a player and replaces chosen answers: (task kind, nth ask of that kind) -> answer."""

    def __init__(self, inner: Agent, answers: dict[tuple[str, int], object]) -> None:
        self._inner, self._answers = inner, answers
        self._asked: dict[str, int] = {}

    async def act(self, view: PlayerView, task: Task) -> object:
        n = self._asked[task.kind] = self._asked.get(task.kind, 0) + 1
        if (task.kind, n) in self._answers:
            return self._answers[(task.kind, n)]
        return await self._inner.act(view, task)


class Flaky:
    """Spoils answers: bad JSON twice on the first vote, bad schema on the first night target,
    and a crash on the first wolf chat."""

    def __init__(self, inner: Agent) -> None:
        self._inner = inner
        self._asked: dict[str, int] = {}

    async def act(self, view: PlayerView, task: Task) -> object:
        n = self._asked[task.kind] = self._asked.get(task.kind, 0) + 1
        if task.kind == "vote" and n <= 2:
            return "this is not json"
        if task.kind == "night_target" and n == 1:
            return {"target": 123}
        if task.kind == "wolf_chat" and n == 1:
            raise RuntimeError("model timed out")
        return await self._inner.act(view, task)


def fake_seer() -> dict[str, Agent]:
    """Round 1: wolf Fay claims to be the Seer and accuses Bo, who answers. Everyone then votes
    Bo out (Bo votes Fay). Afterwards the village votes the wolves out as usual."""
    claim = BidAction(
        bid=3,
        message="I am the Seer. I checked Bo last night: wolf.",
        intent="accuse",
        target="Bo",
    )
    reply = BidAction(bid=0, message="Fay is lying, I am not a wolf.")
    agents = table()
    agents["Fay"] = Script(agents["Fay"], {("bid", 1): claim, ("vote", 1): VoteAction(target="Bo")})
    agents["Bo"] = Script(agents["Bo"], {("bid", 2): reply, ("vote", 1): VoteAction(target="Fay")})
    for name in ("Gus", "Ada", "Eve", "Cy", "Hal"):
        agents[name] = Script(agents[name], {("vote", 1): VoteAction(target="Bo")})
    return agents


def flaky() -> dict[str, Agent]:
    return {name: Flaky(agent) for name, agent in table().items()}


@dataclass
class Scenario:
    agents: Callable[[], dict[str, Agent]]
    winner: Team
    rounds: int
    clean: bool = True


SCENARIOS = {
    "village wins by votes": Scenario(table, Team.VILLAGE, 2),
    "wolves win by kills": Scenario(lambda: table(vote_wolves=False), Team.WOLVES, 4),
    "round limit gives the village the win": Scenario(
        lambda: table(kill=False, vote_wolves=False), Team.VILLAGE, 6
    ),
    "doctor saves every night": Scenario(
        lambda: table(protect=True, vote_wolves=False), Team.VILLAGE, 6
    ),
    "fake seer claim": Scenario(fake_seer, Team.VILLAGE, 3),
    "rejected and crashed answers": Scenario(flaky, Team.VILLAGE, 3, clean=False),
}


def play(name: str) -> GameLog:
    return to_log(asyncio.run(play_game(SEED, None, SCENARIOS[name].agents())))


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_each_scripted_game_ends_as_worked_out_by_hand(name: str) -> None:
    log, expected = play(name), SCENARIOS[name]
    assert (log.winner, log.rounds, log.stats.clean) == (
        expected.winner,
        expected.rounds,
        expected.clean,
    )


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_each_scripted_game_replays_exactly(name: str) -> None:
    assert replays_exactly(play(name))


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_each_scripted_game_log_is_canonical_json(name: str) -> None:
    text = play(name).to_json()
    assert text == json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")) + "\n"


def test_the_doctor_saving_the_target_changes_who_wins() -> None:
    assert play("doctor saves every night").winner is not play("wolves win by kills").winner


def test_the_fake_seer_gets_an_innocent_player_voted_out_in_round_one() -> None:
    log = play("fake seer claim")
    claim = next(e for e in log.events if isinstance(e, Speech) and "Seer" in e.text)
    assert (claim.speaker, claim.paid, claim.reply) == ("Fay", 3, False)
    reply = next(e for e in log.events if isinstance(e, Speech) and e.reply)
    assert (reply.speaker, reply.paid) == ("Bo", 0)
    first_removal = next(e for e in log.events if isinstance(e, Removal))
    assert first_removal.player == "Bo"
    roles = {p.name: p.role for p in log.players}
    assert roles["Bo"] is Role.VILLAGER and roles["Fay"] is Role.WEREWOLF


def test_the_wolves_first_kill_is_the_seer_in_the_scripted_games() -> None:
    first_death = next(e for e in play("village wins by votes").events if isinstance(e, Death))
    assert first_death.player == "Di"


def test_the_rejected_answers_game_still_finishes_and_counts_every_problem() -> None:
    stats = play("rejected and crashed answers").stats
    assert stats.rejected > 0 and stats.failed_calls > 0
    assert stats.rejected <= stats.responses
