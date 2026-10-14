"""What one player remembers between calls. It lives in the agent, never in the game state."""

import json
from collections import deque

from werewolf.engine.actions import Belief


class PlayerMemory:
    """A belief table, a round summary, and (optionally) the player's last few private notes.

    Everything here is private to one player and is only ever shown back to that player.
    """

    def __init__(self, keep_notes: int = 0) -> None:
        self.summary = ""
        self.beliefs: dict[str, Belief] = {}
        self.notes: deque[str] = deque(maxlen=keep_notes)  # keep_notes=0 keeps nothing

    def remember(self, kind: str, action_json: str) -> None:
        """Take in a valid answer of this kind of question (as the engine's action JSON)."""
        data = json.loads(action_json)
        if kind == "memory":
            summary = str(data.get("summary", "")).strip()
            if summary:  # an empty summary keeps the old one
                self.summary = summary
        for player, belief in data.get("beliefs", {}).items():
            self.beliefs[player] = Belief(**belief)
        note = str(data.get("note", "")).strip()
        if note:
            self.notes.append(note)
