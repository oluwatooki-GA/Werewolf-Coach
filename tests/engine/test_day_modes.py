import asyncio

import pytest

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import Agent, BidAction, BidTask, Task
from werewolf.engine.day import run_day
from werewolf.engine.events import Listening, Speech
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings, SpeakingMode
from werewolf.engine.views import PlayerView

DEFAULTS = Settings(speaking_turns=8, tokens_per_day=3)  # the rules these tests were written for


def game(mode: SpeakingMode, seed: int = 1) -> GameState:
    return new_game(
        seed=seed,
        settings=Settings(speaking_mode=mode, speaking_turns=8, tokens_per_day=3),
    )


def names(state: GameState) -> list[str]:
    return [p.name for p in state.players]


def bidders(
    state: GameState,
    script: dict[str, list[BidAction]],
    seen: list[tuple[str, BidTask]] | None = None,
) -> dict[str, Agent]:
    queues = {n: list(script.get(n, [])) for n in names(state)}

    def make(name: str) -> ScriptedAgent:
        def respond(view: PlayerView, task: Task) -> object:
            assert isinstance(task, BidTask)
            if seen is not None:
                seen.append((name, task))
            return queues[name].pop(0) if queues[name] else BidAction(bid=0)

        return ScriptedAgent(respond)

    return {n: make(n) for n in names(state)}


def say(bid: int, text: str = "hello", **kw: object) -> BidAction:
    return BidAction.model_validate({"bid": bid, "message": text, **kw})


def play(state: GameState, agents: dict[str, Agent]) -> list[Speech]:
    asyncio.run(run_day(state, agents))
    return [e for e in state.events if isinstance(e, Speech)]


def listeners(state: GameState) -> list[str]:
    return [e.player for e in state.events if isinstance(e, Listening)]


# --- fixed order -----------------------------------------------------------------------------


def test_fixed_order_has_living_players_speak_in_seat_order() -> None:
    state = game(SpeakingMode.FIXED_ORDER)
    script = {n: [say(0, f"{n} speaks")] for n in names(state)}
    speeches = play(state, bidders(state, script))
    assert [s.speaker for s in speeches] == names(state)
    assert all(s.paid == 0 and not s.reply for s in speeches)


def test_fixed_order_asks_only_the_speaker_each_turn_and_no_bids_are_made() -> None:
    state = game(SpeakingMode.FIXED_ORDER)
    seen: list[tuple[str, BidTask]] = []
    script = {n: [say(0, "hi")] for n in names(state)}
    play(state, bidders(state, script, seen))
    assert len(state.calls) == 8
    assert [who for who, _ in seen] == names(state)
    assert all(t.free and t.max_bid == 0 for _, t in seen)


def test_fixed_order_skips_the_dead_and_repeats_the_seat_order() -> None:
    state = game(SpeakingMode.FIXED_ORDER)
    for p in state.players[3:]:
        p.alive = False
    script = {n: [say(0, "a"), say(0, "b"), say(0, "c")] for n in names(state)}
    speeches = play(state, bidders(state, script))
    living = names(state)[:3]
    assert [s.speaker for s in speeches] == (living * 3)[:8]


def test_fixed_order_gives_no_free_reply_after_an_accusation() -> None:
    state = game(SpeakingMode.FIXED_ORDER)
    first, second, third = names(state)[:3]
    script = {first: [say(0, "accuse", intent="accuse", target=third)]}
    seen: list[tuple[str, BidTask]] = []
    speeches = play(state, bidders(state, {**script, second: [say(0, "next")]}, seen))
    assert [s.speaker for s in speeches][:2] == [first, second]
    assert all(t.reply_to is None for _, t in seen)


def test_fixed_order_a_silent_player_is_shown_as_listening() -> None:
    state = game(SpeakingMode.FIXED_ORDER)
    script = {n: [say(0, "hi")] for n in names(state)[1:]}
    speeches = play(state, bidders(state, script))
    assert listeners(state) == [names(state)[0]]
    assert len(speeches) == 7


# --- free bidding -----------------------------------------------------------------------------


def test_free_bidding_allows_bids_up_to_four() -> None:
    state = game(SpeakingMode.FREE_BID)
    a, b = names(state)[:2]
    seen: list[tuple[str, BidTask]] = []
    speeches = play(state, bidders(state, {a: [say(4, "loud")], b: [say(3)]}, seen))
    assert [s.speaker for s in speeches] == [a]
    assert all(t.max_bid == 4 and not t.free for _, t in seen)


def test_free_bidding_rejects_a_bid_of_five() -> None:
    state = game(SpeakingMode.FREE_BID)
    a = names(state)[0]
    speeches = play(state, bidders(state, {a: [say(5), say(5)]}))
    assert speeches == []
    assert next(c for c in state.calls if c.player == a).failed


def test_free_bidding_costs_nothing_so_a_player_can_win_every_turn() -> None:
    state = game(SpeakingMode.FREE_BID)
    a = names(state)[0]
    speeches = play(state, bidders(state, {a: [say(4, "again")] * 8}))
    assert [s.speaker for s in speeches] == [a] * 8
    assert all(s.paid == 0 for s in speeches)


def test_free_bidding_ties_go_to_least_spoken_then_the_rng() -> None:
    for seed in range(15):
        state = game(SpeakingMode.FREE_BID, seed)
        a, b = names(state)[:2]
        script = {a: [say(2, "1"), say(2, "2")], b: [BidAction(bid=0), say(2, "3")]}
        assert [s.speaker for s in play(state, bidders(state, script))] == [a, b], seed

    def winner(seed: int) -> bool:
        state = game(SpeakingMode.FREE_BID, seed)
        a, b = names(state)[:2]
        return play(state, bidders(state, {a: [say(2)], b: [say(2)]}))[0].speaker == a

    assert {winner(s) for s in range(30)} == {True, False}


def test_free_bidding_all_listening_ends_the_day() -> None:
    state = game(SpeakingMode.FREE_BID)
    assert play(state, bidders(state, {})) == []
    assert len(state.calls) == 8


def test_free_bidding_gives_no_free_reply() -> None:
    state = game(SpeakingMode.FREE_BID)
    a, b = names(state)[:2]
    seen: list[tuple[str, BidTask]] = []
    play(state, bidders(state, {a: [say(1, "x", intent="accuse", target=b)]}, seen))
    assert all(t.reply_to is None for _, t in seen)


# --- switching --------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(SpeakingMode))
def test_the_three_modes_switch_by_setting_only(mode: SpeakingMode) -> None:
    def respond(view: PlayerView, task: Task) -> object:
        assert isinstance(task, BidTask)
        return say(0 if task.free else 1, f"{view.name} here")  # answer the task as asked

    state = game(mode)
    speeches = play(state, {n: ScriptedAgent(respond) for n in names(state)})
    assert 1 <= len(speeches) <= state.settings.speaking_turns
