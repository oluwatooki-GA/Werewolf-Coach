"""One player's prompt-building state: strategy card, round-summary setting, and private memory.

The live agent and the "show me the prompt" tool both use this, so they can never disagree.
"""

from werewolf.agents.memory import PlayerMemory
from werewolf.agents.prompt import build_messages
from werewolf.engine.actions import Task
from werewolf.engine.views import PlayerView


class Prompter:
    def __init__(self, *, card: str = "", summarize: bool = False, keep_notes: int = 0) -> None:
        self._card = card
        self._summarize = summarize
        self.memory = PlayerMemory(keep_notes)

    def messages(self, view: PlayerView, task: Task) -> list[dict[str, str]]:
        return build_messages(
            view,
            task,
            card=self._card,
            beliefs=self.memory.beliefs,
            summary=self.memory.summary,
            notes=list(self.memory.notes),
            from_round=view.round if self._summarize else 1,  # older rounds live in the summary
        )

    def learn(self, kind: str, action_json: str) -> None:
        """Take in a valid answer, so the next prompt shows its beliefs, summary and note."""
        self.memory.remember(kind, action_json)
