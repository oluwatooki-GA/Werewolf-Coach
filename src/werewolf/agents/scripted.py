"""Fake agents for tests. They answer from a function or a fixed list, with no model."""

from collections.abc import Callable, Collection

from werewolf.engine.actions import (
    BidAction,
    BidTask,
    ChatAction,
    NightTargetTask,
    TargetAction,
    Task,
    VoteAction,
    VoteTask,
)
from werewolf.engine.views import PlayerView, Role


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


def policy(
    wolves: Collection[str],
    *,
    kill: bool = True,
    protect: bool = False,
    vote_wolves: bool = True,
) -> ScriptedAgent:
    """One fake player that never talks. Wolves kill the first living non-wolf; the Doctor protects
    that same player; the village votes for a wolf. It knows who the wolves are, so it cheats."""

    def respond(view: PlayerView, task: Task) -> object:
        if isinstance(task, BidTask):
            return BidAction(bid=0, message="talk" if task.free else "")
        if isinstance(task, NightTargetTask):
            prey = [n for n in task.options if n not in wolves]
            if task.purpose == "kill" and kill and prey:
                return TargetAction(target=prey[0])
            if task.purpose == "protect" and protect and prey:
                return TargetAction(target=prey[0])
            return TargetAction(target=None)
        if isinstance(task, VoteTask):
            living = [w for w in wolves if w in task.options]
            if vote_wolves and view.role is not Role.WEREWOLF and living:
                return VoteAction(target=living[0], reason="wolf")
            return VoteAction(target=None)
        return ChatAction(text="grr")

    return ScriptedAgent(respond)
