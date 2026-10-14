"""One player's prompt-building state: strategy card, round-summary setting, and private memory.

The live agent and the "show me the prompt" tool both use this, so they can never disagree.

Two layouts:
- "stateless": every call is a fresh two-message chat, rebuilt from the log and the memory.
- "conversation": one chat per player per round. Each question adds only what is new, and the
  model's earlier answers stay in the chat as its own turns. Every prompt then starts with the
  previous prompt, so a provider's prompt cache can serve the whole shared start.
"""

from typing import Literal

from werewolf.agents.memory import PlayerMemory
from werewolf.agents.prompt import build_messages, build_turn, system_message
from werewolf.agents.wire import to_wire_json
from werewolf.engine.actions import ACTION_FOR, Task
from werewolf.engine.views import PlayerView

Layout = Literal["stateless", "conversation"]
RAW_KEPT = 400  # characters of an unreadable answer that stay in the chat


class Prompter:
    def __init__(
        self,
        *,
        card: str = "",
        summarize: bool = False,
        keep_notes: int = 0,
        layout: Layout = "stateless",
    ) -> None:
        self._card = card
        self._summarize = summarize
        self._layout = layout
        self.memory = PlayerMemory(keep_notes)
        self._round = 0  # the round the current chat belongs to
        self._seen = 0  # how many events of the view the chat has shown
        self._chat: list[dict[str, str]] = []

    def messages(self, view: PlayerView, task: Task) -> list[dict[str, str]]:
        from_round = view.round if self._summarize else 1  # older rounds live in the summary
        if self._layout == "stateless":
            return build_messages(
                view,
                task,
                card=self._card,
                beliefs=self.memory.beliefs,
                summary=self.memory.summary,
                notes=list(self.memory.notes),
                from_round=from_round,
            )
        if view.round != self._round:  # a new round starts a new chat, seeded by the summary
            self._round, self._seen, self._chat = view.round, 0, []
        seen = self._seen if self._chat else None  # the first message carries everything
        turn = build_turn(view, task, summary=self.memory.summary, from_round=from_round, seen=seen)
        if not task.error:
            self._seen = len(view.events)
        self._chat.append({"role": "user", "content": turn})
        return [{"role": "system", "content": system_message(view, self._card)}, *self._chat]

    def answered(self, kind: str, text: str) -> None:
        """The model's answer, readable or not. In a chat it becomes the model's own turn."""
        if self._layout == "conversation":
            self._chat.append({"role": "assistant", "content": _as_turn(kind, text)})

    def learn(self, kind: str, action_json: str) -> None:
        """Take in a valid answer, so the next prompt shows its beliefs, summary and note."""
        self.memory.remember(kind, action_json)


def _as_turn(kind: str, text: str) -> str:
    """An accepted answer is shown back the way the model writes answers; anything else is kept
    short, as it came."""
    try:
        ACTION_FOR[kind].model_validate_json(text)
        return to_wire_json(kind, text)
    except (ValueError, KeyError):
        return text[:RAW_KEPT]
