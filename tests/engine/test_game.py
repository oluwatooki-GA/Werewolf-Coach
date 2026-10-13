import asyncio

import pytest

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import (
    Agent,
    BidAction,
    BidTask,
    ChatAction,
    NightTargetTask,
    TargetAction,
    Task,
    VoteAction,
    VoteTask,
)
from werewolf.engine.events import Death, GameOver, Removal
from werewolf.engine.game import play_game
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings, SpeakingMode
from werewolf.engine.views import PlayerView

SEED = 1


def policy(
    seed: int = SEED,
    kill: bool = True,
    protect: bool = False,
    vote_wolves: bool = True,
) -> dict[str, Agent]:
    """Scripted players. Wolves kill the first living non-wolf; the Doctor can protect that same
    player; everyone else votes for a wolf (they cheat: they know who the wolves are)."""
    wolves = [p.name for p in new_game(seed).players if p.role is Role.WEREWOLF]

    def respond(view: PlayerView, task: Task) -> object:
        match task:
            case _ if isinstance(task, BidTask):
                return BidAction(bid=0, message="talk" if task.free else "")
            case _ if isinstance(task, NightTargetTask):
                prey = [n for n in task.options if n not in wolves]
                if task.purpose == "kill":
                    return TargetAction(target=prey[0] if kill else None)
                if task.purpose == "protect":
                    return TargetAction(target=prey[0] if protect else None)
                return TargetAction(target=None)
            case _ if isinstance(task, VoteTask):
                living_wolves = [w for w in wolves if w in task.options]
                if vote_wolves and view.role is not Role.WEREWOLF and living_wolves:
                    return VoteAction(target=living_wolves[0], reason="wolf")
                return VoteAction(target=None)
            case _:
                return ChatAction(text="grr")

    return {p.name: ScriptedAgent(respond) for p in new_game(seed).players}


def play(agents: dict[str, Agent], seed: int = SEED, settings: Settings | None = None) -> GameState:
    return asyncio.run(play_game(seed, settings or Settings(), agents))


def test_the_village_wins_by_voting_out_both_wolves() -> None:
    state = play(policy())
    assert state.winner is Team.VILLAGE
    assert state.round == 2
    removed = [e.player for e in state.events if isinstance(e, Removal)]
    assert sorted(removed) == sorted(p.name for p in state.players if p.role is Role.WEREWOLF)


def test_the_wolves_win_by_killing_until_they_equal_the_village() -> None:
    state = play(policy(vote_wolves=False))
    assert state.winner is Team.WOLVES
    assert sum(p.alive for p in state.players if p.role is not Role.WEREWOLF) == 2
    assert state.round == 4  # four night kills take 6 down to 2


def test_with_no_kills_and_no_votes_the_round_limit_gives_the_village_the_win() -> None:
    state = play(policy(kill=False, vote_wolves=False))
    assert state.winner is Team.VILLAGE
    assert state.round == 6
    assert all(p.alive for p in state.players)


def test_the_doctor_saving_the_target_every_night_changes_the_outcome() -> None:
    saved = play(policy(protect=True, vote_wolves=False))
    unsaved = play(policy(protect=False, vote_wolves=False))
    assert (saved.winner, unsaved.winner) == (Team.VILLAGE, Team.WOLVES)


def test_the_game_ends_with_a_public_game_over_event() -> None:
    state = play(policy())
    assert state.events[-1] == GameOver(round=state.round, winner=Team.VILLAGE)


def test_the_dead_are_never_asked_to_bid_or_vote_again() -> None:
    state = play(policy())
    last_round_asked: dict[str, int] = {}
    for e in state.events:
        if isinstance(e, Death):  # killed at night: gone before that round's day
            last_round_asked.setdefault(e.player, e.round - 1)
        if isinstance(e, Removal):  # removed by that round's vote: had already voted
            last_round_asked.setdefault(e.player, e.round)
    assert last_round_asked
    for call in state.calls:
        if call.player in last_round_asked and call.task["kind"] in ("bid", "vote"):
            assert call.round <= last_round_asked[call.player], call


def test_the_same_seed_and_agents_play_the_same_game() -> None:
    first, second = play(policy()), play(policy())
    assert first.events == second.events
    assert first.calls == second.calls


def test_a_different_seed_plays_a_different_game() -> None:
    games = {tuple(play(policy(seed=s), seed=s).events) for s in range(4)}
    assert len(games) > 1


@pytest.mark.parametrize("mode", list(SpeakingMode))
def test_a_whole_game_runs_in_every_speaking_mode(mode: SpeakingMode) -> None:
    state = play(policy(), settings=Settings(speaking_mode=mode))
    assert state.winner is Team.VILLAGE


def test_a_game_never_runs_past_the_round_limit() -> None:
    state = play(policy(kill=False, vote_wolves=False), settings=Settings(max_rounds=3))
    assert state.winner is Team.VILLAGE
    assert state.round == 3
