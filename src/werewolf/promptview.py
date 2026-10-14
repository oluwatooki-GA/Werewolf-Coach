"""Show the prompts a saved game's players saw, by playing the game again from its log.

The log keeps answers, not prompts. Playing the game again with those answers gives every player
the same views and the same memory as before, so the same prompts can be built again. It uses
today's prompt code: a game played before a prompt change shows today's wording.
It lives outside `agents/` because it reads the log, which holds every secret.
"""

import asyncio
import json
from dataclasses import dataclass

from werewolf.agents.prompter import Prompter
from werewolf.engine.actions import ACTION_FOR, Agent, Reply, Task
from werewolf.engine.events import Speech
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replayers
from werewolf.engine.views import PlayerView

NOTE = (
    "(Rebuilt from the saved answers with today's prompt code. A game played before a change to "
    "the prompts shows the new wording, not what its players saw.)"
)


@dataclass
class Rebuilt:
    player: str
    round: int
    kind: str
    messages: list[dict[str, str]]
    answer: str
    retry: bool  # the engine rejected the first answer and asked again
    spoke: bool = False  # this answer's message was posted to the table


class _Rebuilder:
    def __init__(self, name: str, inner: Agent, prompter: Prompter, sink: list[Rebuilt]) -> None:
        self._name, self._inner, self._prompter, self._sink = name, inner, prompter, sink

    async def act(self, view: PlayerView, task: Task) -> object:
        messages = self._prompter.messages(view, task)
        out = await self._inner.act(view, task)
        raw = out.text if isinstance(out, Reply) else out
        text = raw if isinstance(raw, str) else json.dumps(raw)
        self._sink.append(
            Rebuilt(self._name, view.round, task.kind, messages, text, task.error is not None)
        )
        try:  # the live agent only remembers answers it could read
            ACTION_FOR[task.kind].model_validate_json(text)
            self._prompter.learn(task.kind, text)
        except ValueError:
            pass
        return out


def rebuild(log: GameLog, keep_notes: int = 0) -> list[Rebuilt]:
    """Every prompt of the game in the order it was sent. `keep_notes` must match the run."""
    found: list[Rebuilt] = []
    agents = {
        name: _Rebuilder(
            name,
            inner,
            Prompter(summarize=log.settings.summarize_rounds, keep_notes=keep_notes),
            found,
        )
        for name, inner in replayers(log).items()
    }
    state = asyncio.run(play_game(log.seed, log.settings, agents))
    posted = {(e.speaker, e.round, e.text) for e in state.events if isinstance(e, Speech)}
    for item in found:
        if item.kind == "bid":
            message = json.loads(item.answer).get("message", "") if item.answer[:1] == "{" else ""
            item.spoke = (item.player, item.round, message) in posted
    return found


def render(
    items: list[Rebuilt],
    player: str,
    round_: int | None = None,
    kind: str | None = None,
    spoke: bool = False,
) -> str:
    """The chosen prompts as text. The system message is printed once; it never changes."""
    chosen = [
        i
        for i in items
        if i.player == player
        and (round_ is None or i.round == round_)
        and (kind is None or i.kind == kind)
        and (not spoke or i.spoke)
    ]
    if not chosen:
        return f"No prompt matches ({player}, round {round_ or 'any'}, {kind or 'any kind'})."
    lines = [NOTE]
    for n, item in enumerate(chosen):
        tags = (" (retry)" if item.retry else "") + (", message posted" if item.spoke else "")
        lines += ["", f"===== {item.player}, round {item.round}, {item.kind}{tags} ====="]
        system, user = item.messages[0]["content"], item.messages[1]["content"]
        lines += ["----- SYSTEM -----", system] if n == 0 else ["----- SYSTEM: same as above -----"]
        lines += ["----- USER -----", user, "----- ANSWER -----", item.answer]
    return "\n".join(lines)
