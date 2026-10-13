"""Fake agents for tests. They answer from a function or a fixed list, with no model."""
from collections.abc import Callable

from werewolf.engine.actions import Task
from werewolf.engine.views import PlayerView


class ScriptedAgent:
    def __init__(self, respond: Callable[[PlayerView, Task], object]) -> None:
        self._respond = respond

    async def act(self, view: PlayerView, task: Task) -> object:
        return self._respond(view, task)


def from_queue(responses: list[object]) -> ScriptedAgent:
    """Answer with each response in order. Asking more often than that raises."""
    queue = list(responses)

    def respond(view: PlayerView, task: Task) -> object:
        return queue.pop(0)

    return ScriptedAgent(respond)
