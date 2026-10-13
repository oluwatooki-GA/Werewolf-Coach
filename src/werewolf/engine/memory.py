"""End of a round: every living player rewrites its own short summary of the game so far."""

from collections.abc import Callable, Mapping

from werewolf.engine.actions import Action, Agent, MemoryAction, MemoryTask
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.state import GameState


def memory_check(limit: int) -> Callable[[Action], str | None]:
    def check(action: Action) -> str | None:
        if isinstance(action, MemoryAction) and len(action.summary) <= limit:
            return None
        return f"the summary must be at most {limit} characters"

    return check


async def run_memory(state: GameState, agents: Mapping[str, Agent]) -> None:
    """The answers stay with the agents (private memory); the engine only asks and logs."""
    limit = state.settings.max_summary_chars
    alive = [p.name for p in state.players if p.alive]
    task = MemoryTask(max_chars=limit)
    await ask_many(state, agents, [Request(name, task, memory_check(limit)) for name in alive])
