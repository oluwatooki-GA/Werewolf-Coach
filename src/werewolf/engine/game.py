from collections.abc import Mapping

from werewolf.engine.actions import Agent
from werewolf.engine.day import run_day
from werewolf.engine.events import GameOver
from werewolf.engine.night import run_night
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings
from werewolf.engine.vote import run_vote
from werewolf.engine.win import winner


async def play_game(seed: int, settings: Settings | None, agents: Mapping[str, Agent]) -> GameState:
    """Play one whole game: night, morning, day, vote, win check, until someone wins."""
    state = new_game(seed, settings)
    while True:
        await run_night(state, agents)
        result = winner(state, round_complete=False)
        if result is None:
            await run_day(state, agents)
            await run_vote(state, agents)
            result = winner(state, round_complete=True)
        if result is not None:
            state.winner = result
            state.events.append(GameOver(round=state.round, winner=result))
            return state
        state.round += 1
