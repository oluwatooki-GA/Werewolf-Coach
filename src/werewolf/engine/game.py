from collections.abc import Callable, Mapping

from werewolf.engine.actions import Agent
from werewolf.engine.day import run_day
from werewolf.engine.events import GameOver
from werewolf.engine.memory import run_memory
from werewolf.engine.night import run_night
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings
from werewolf.engine.vote import run_vote
from werewolf.engine.win import winner


async def play_game(
    seed: int,
    settings: Settings | None,
    agents: Mapping[str, Agent],
    on_start: Callable[[GameState], None] | None = None,
) -> GameState:
    """Play one whole game: night, morning, day, vote, win check, until someone wins.

    `on_start` is called once with the new state before the first night, so a caller can read
    the events and calls as they pile up. It changes nothing about how the game is played."""
    state = new_game(seed, settings)
    if on_start is not None:
        on_start(state)
    while True:
        await run_night(state, agents)
        result = winner(state, round_complete=False)
        if result is None:
            await run_day(state, agents)
            await run_vote(state, agents)
            result = winner(state, round_complete=True)
            if result is None and state.settings.summarize_rounds:
                await run_memory(state, agents)
        if result is not None:
            state.winner = result
            state.events.append(GameOver(round=state.round, winner=result))
            return state
        state.round += 1
