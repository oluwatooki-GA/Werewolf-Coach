"""A caller can be handed the game's state the moment it is made, to read it while it is played."""

import asyncio

from werewolf.agents.scripted import policy
from werewolf.engine.actions import Agent
from werewolf.engine.game import play_game
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings


def table(seed: int) -> dict[str, Agent]:
    players = new_game(seed).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    return {p.name: policy(wolves) for p in players}


def test_on_start_is_called_once_with_the_state_before_anything_has_happened() -> None:
    seen: list[tuple[GameState, int, int]] = []

    def on_start(state: GameState) -> None:
        seen.append((state, len(state.events), len(state.calls)))

    final = asyncio.run(play_game(3, None, table(3), on_start=on_start))
    assert len(seen) == 1
    state, events, calls = seen[0]
    assert state is final  # the same object keeps filling up as the game is played
    assert (events, calls) == (0, 0)
    assert final.events and final.winner is not None


def test_the_game_is_the_same_with_or_without_the_hook() -> None:
    settings = Settings(wolf_chat_messages=5)
    plain = asyncio.run(play_game(3, settings, table(3)))
    hooked = asyncio.run(play_game(3, settings, table(3), on_start=lambda state: None))
    assert plain.events == hooked.events and plain.winner == hooked.winner
