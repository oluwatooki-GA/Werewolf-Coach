import asyncio
import random

import pytest

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import Agent, BidAction, BidTask, Task
from werewolf.engine.day import run_day
from werewolf.engine.events import Listening, Speech
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings
from werewolf.engine.views import PlayerView, make_view


def bidders(
    state: GameState,
    script: dict[str, list[BidAction]],
    seen: list[tuple[str, BidTask]] | None = None,
) -> dict[str, Agent]:
    """Each player answers from its own list, in the order it is asked, then bids 0."""
    queues = {p.name: list(script.get(p.name, [])) for p in state.players}

    def make(name: str) -> ScriptedAgent:
        def respond(view: PlayerView, task: Task) -> object:
            assert isinstance(task, BidTask)
            if seen is not None:
                seen.append((name, task))
            return queues[name].pop(0) if queues[name] else BidAction(bid=0)

        return ScriptedAgent(respond)

    return {p.name: make(p.name) for p in state.players}


def play_day(state: GameState, agents: dict[str, Agent]) -> None:
    asyncio.run(run_day(state, agents))


def names(state: GameState) -> list[str]:
    return [p.name for p in state.players]


def speeches(state: GameState) -> list[Speech]:
    return [e for e in state.events if isinstance(e, Speech)]


def listeners(state: GameState) -> list[str]:
    return [e.player for e in state.events if isinstance(e, Listening)]


def cite(speaker: str, line: str = "R1-1") -> dict[str, str]:
    return {"line": line, "speaker": speaker}


def say(bid: int, text: str = "hello", **kw: object) -> BidAction:
    return BidAction.model_validate({"bid": bid, "message": text, **kw})


def test_highest_bid_speaks_and_pays_exactly_its_bid() -> None:
    state = new_game(seed=1)
    a, b, c = names(state)[:3]
    seen: list[tuple[str, BidTask]] = []
    script = {a: [say(1), BidAction(bid=0)], b: [say(3, "mine"), BidAction(bid=0)], c: [say(2)]}
    play_day(state, bidders(state, script, seen))
    assert [(s.speaker, s.paid, s.text) for s in speeches(state)] == [(b, 3, "mine")]
    second_turn = [task for who, task in seen if who == b][1]
    assert second_turn.max_bid == 0


def test_bid_ties_go_to_least_spoken() -> None:
    for seed in range(20):  # must hold for every seed, so luck cannot pass it
        state = new_game(seed=seed)
        a, b = names(state)[:2]
        script = {a: [say(1, "first"), say(1, "again")], b: [BidAction(bid=0), say(1, "me")]}
        play_day(state, bidders(state, script))
        assert [s.speaker for s in speeches(state)] == [a, b], seed


def test_a_tie_between_equally_quiet_players_is_settled_by_the_seeded_rng() -> None:
    def winner(seed: int) -> str:
        state = new_game(seed=seed)
        a, b = names(state)[:2]
        play_day(state, bidders(state, {a: [say(1)], b: [say(1)]}))
        return "first" if speeches(state)[0].speaker == a else "second"

    assert all(winner(seed) == winner(seed) for seed in range(8))
    assert {winner(seed) for seed in range(30)} == {"first", "second"}


def test_zero_bid_means_listening() -> None:
    state = new_game(seed=1)
    a = names(state)[0]
    play_day(state, bidders(state, {a: [say(1)]}))
    assert [s.speaker for s in speeches(state)] == [a]
    first_turn_listeners = listeners(state)[:7]
    assert sorted(first_turn_listeners) == sorted(n for n in names(state) if n != a)


def test_all_listening_ends_the_day() -> None:
    state = new_game(seed=1)
    play_day(state, bidders(state, {}))
    assert speeches(state) == []
    assert len(state.calls) == 8  # one turn, then the day ends
    assert sorted(listeners(state)) == sorted(names(state))


def test_the_day_also_ends_early_after_a_quiet_turn_that_follows_speech() -> None:
    state = new_game(seed=1)
    play_day(state, bidders(state, {names(state)[0]: [say(1)]}))
    assert len(speeches(state)) == 1
    assert len(state.calls) == 16  # turn 1 spoke, turn 2 everyone listened


def test_the_day_stops_at_the_speaking_turn_limit() -> None:
    state = new_game(seed=1, settings=Settings(speaking_turns=3))
    script = {n: [say(1)] * 8 for n in names(state)}
    play_day(state, bidders(state, script))
    assert len(speeches(state)) == 3


def test_right_of_reply_once_per_day() -> None:
    state = new_game(seed=1)
    a, b, c = names(state)[:3]
    script = {
        a: [say(2, "b is a wolf", intent="accuse", target=b)],
        b: [BidAction(bid=0), say(0, "no I am not")],  # 2nd answer is the free reply
        c: [BidAction(bid=0), say(1, "b again", intent="accuse", target=b, cites=[cite(a)])],
    }
    seen: list[tuple[str, BidTask]] = []
    play_day(state, bidders(state, script, seen))
    replies = [(who, t.reply_to) for who, t in seen if t.reply_to is not None]
    assert replies == [(b, a)]  # one reply in total: c's later accusation of b earns none
    assert [s.reply for s in speeches(state)] == [False, True, False]
    assert speeches(state)[1].paid == 0
    assert len(state.calls) == 8 + 1 + 8 + 8  # turn 3 was a normal bidding turn, turn 4 all quiet


def test_only_an_accuse_intent_with_a_target_gives_a_reply() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    script = {a: [say(1, "defending", intent="defend", target=b), say(1, "bare", intent="accuse")]}
    seen: list[tuple[str, BidTask]] = []
    play_day(state, bidders(state, script, seen))
    assert all(t.reply_to is None for _, t in seen)


def test_a_free_reply_counts_as_one_of_the_speaking_turns() -> None:
    state = new_game(seed=1, settings=Settings(speaking_turns=2))
    a, b = names(state)[:2]
    script = {
        a: [say(1, "accuse", intent="accuse", target=b)],
        b: [BidAction(bid=0), say(0, "reply")],
    }
    play_day(state, bidders(state, script))
    assert len(speeches(state)) == 2
    assert len(state.calls) == 8 + 1


def test_tokens_lost_at_nightfall() -> None:
    state = new_game(seed=1)
    a = names(state)[0]
    seen: list[tuple[str, BidTask]] = []
    play_day(state, bidders(state, {a: [say(3)]}, seen))
    state.round += 1  # nightfall, then a new day
    seen.clear()
    play_day(state, bidders(state, {}, seen))
    assert {t.max_bid for _, t in seen} == {3}


def test_no_overbidding() -> None:
    state = new_game(seed=1)
    a = names(state)[0]
    script = {a: [say(2), say(3, "too much"), say(3, "still too much")]}
    seen: list[tuple[str, BidTask]] = []
    play_day(state, bidders(state, script, seen))
    assert [s.paid for s in speeches(state)] == [2]
    overbid = [c for c in state.calls if c.player == a][1]
    assert overbid.failed and overbid.rejected == 2
    assert "at most 1" in overbid.errors[0]
    assert [t.error is not None for who, t in seen if who == a][1:3] == [False, True]


def test_a_bid_above_zero_needs_a_message() -> None:
    state = new_game(seed=1)
    a = names(state)[0]
    play_day(state, bidders(state, {a: [say(1, ""), say(1, "")]}))
    assert speeches(state) == []
    assert next(c for c in state.calls if c.player == a).failed


def test_all_randomness_through_seeded_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("global random used")

    for fn in ("random", "choice", "shuffle", "randint", "randrange", "sample", "choices",
               "uniform", "getrandbits", "seed"):  # fmt: skip
        monkeypatch.setattr(random, fn, forbidden)

    def day(seed: int) -> list[Speech]:
        state = new_game(seed=seed)
        script = {n: [say(1, n)] * 3 for n in names(state)}  # ties on every turn
        play_day(state, bidders(state, script))
        return speeches(state)

    assert day(5) == day(5)
    assert any(day(s) != day(5) for s in range(6, 16))


def test_result_ignores_answer_order() -> None:
    class Slow:
        def __init__(self, inner: Agent, delay: float) -> None:
            self._inner, self._delay = inner, delay

        async def act(self, view: PlayerView, task: Task) -> object:
            await asyncio.sleep(self._delay)
            return await self._inner.act(view, task)

    def day(delays: list[float]) -> tuple[list[Speech], list[str]]:
        state = new_game(seed=2)
        script = {n: [say(1, n)] * 3 for n in names(state)}
        agents = bidders(state, script)
        slowed = {n: Slow(agents[n], d) for n, d in zip(names(state), delays, strict=True)}
        play_day(state, slowed)
        return speeches(state), [c.player for c in state.calls]

    forward = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    assert day(forward) == day(forward[::-1])


def test_the_private_intent_never_reaches_a_view() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    play_day(state, bidders(state, {a: [say(1, "hmm", intent="accuse", target=b)]}))
    for p in state.players:
        assert '"intent"' not in make_view(state, p.name).model_dump_json()
