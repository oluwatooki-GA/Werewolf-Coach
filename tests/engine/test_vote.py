import asyncio

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import Agent, Task, VoteAction, VoteTask
from werewolf.engine.events import NoRemoval, Removal, VoteCast
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState
from werewolf.engine.views import PlayerView
from werewolf.engine.vote import run_vote


def names(state: GameState) -> list[str]:
    return [p.name for p in state.players]


def voters(
    state: GameState,
    choice: dict[str, str | None],
    seen: list[PlayerView] | None = None,
    tasks: list[Task] | None = None,
) -> dict[str, Agent]:
    """Each player votes as listed (anyone not listed abstains)."""

    def make(name: str) -> ScriptedAgent:
        def respond(view: PlayerView, task: Task) -> object:
            if seen is not None:
                seen.append(view)
            if tasks is not None:
                tasks.append(task)
            return VoteAction(target=choice.get(name), reason=f"{name}'s reason")

        return ScriptedAgent(respond)

    return {n: make(n) for n in names(state)}


def vote(state: GameState, agents: dict[str, Agent]) -> None:
    asyncio.run(run_vote(state, agents))


def alive(state: GameState, name: str) -> bool:
    return next(p for p in state.players if p.name == name).alive


def test_the_player_with_the_most_votes_is_removed() -> None:
    state = new_game(seed=1)
    a, b, c, d = names(state)[:4]
    vote(state, voters(state, {a: c, b: c, c: d, d: a}))
    assert not alive(state, c)
    assert [e for e in state.events if isinstance(e, Removal)] == [Removal(round=1, player=c)]


def test_a_tie_for_most_votes_removes_nobody() -> None:
    state = new_game(seed=1)
    a, b, c, d = names(state)[:4]
    vote(state, voters(state, {a: c, b: c, c: a, d: a}))
    assert all(p.alive for p in state.players)
    assert [e for e in state.events if isinstance(e, NoRemoval)] == [NoRemoval(round=1)]


def test_abstaining_counts_as_no_vote() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    vote(state, voters(state, {a: b}))
    assert not alive(state, b)


def test_if_everyone_abstains_nobody_is_removed() -> None:
    state = new_game(seed=1)
    vote(state, voters(state, {}))
    assert all(p.alive for p in state.players)
    assert any(isinstance(e, NoRemoval) for e in state.events)


def test_votes_are_sealed_until_everyone_has_voted() -> None:
    state = new_game(seed=1)
    seen: list[PlayerView] = []
    a, b = names(state)[:2]
    vote(state, voters(state, {a: b, b: a}, seen))
    assert len(seen) == 8
    assert all(not any(isinstance(e, VoteCast) for e in v.events) for v in seen)


def test_votes_are_then_shown_to_everyone_in_seat_order_with_their_reasons() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    vote(state, voters(state, {a: b, b: a}))
    casts = [e for e in state.events if isinstance(e, VoteCast)]
    assert [c.voter for c in casts] == names(state)
    assert casts[0] == VoteCast(round=1, voter=a, target=b, reason=f"{a}'s reason")
    assert casts[2].target is None


def test_a_vote_for_yourself_is_rejected_and_retried() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    tasks: list[Task] = []
    vote(state, voters(state, {a: a}, tasks=tasks))
    record = next(c for c in state.calls if c.player == a)
    assert (record.rejected, record.failed) == (2, True)  # asked twice, then abstained
    assert next(e for e in state.events if isinstance(e, VoteCast) and e.voter == a).target is None
    assert a not in next(t for t in tasks if isinstance(t, VoteTask)).options


def test_the_dead_neither_vote_nor_receive_votes() -> None:
    state = new_game(seed=1)
    a, b, c = names(state)[:3]
    next(p for p in state.players if p.name == c).alive = False
    tasks: list[Task] = []
    vote(state, voters(state, {a: b}, tasks=tasks))
    assert len(tasks) == 7
    assert all(c not in t.options for t in tasks if isinstance(t, VoteTask))
    assert c not in {call.player for call in state.calls}


def test_the_removal_announcement_never_names_a_role() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    vote(state, voters(state, {a: b}))
    text = next(e for e in state.events if isinstance(e, Removal)).model_dump_json()
    assert not any(role in text for role in ("Werewolf", "Seer", "Doctor", "Villager"))
