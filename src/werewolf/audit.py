"""Leak audit: check the prompts a game actually sent against the secrets in its log.

Used by the CI leak test (planted code words) and by real runs (the game's own private texts).
It lives outside `agents/` because it reads the log, which holds every secret.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from werewolf.engine.events import SeerResult, Speech, VoteCast, WolfChat
from werewolf.engine.log import GameLog
from werewolf.engine.roles import Role


@dataclass(frozen=True)
class Leak:
    player: str  # whose prompt held something it should not
    kind: str  # wolf_chat, note, belief, summary, seer_result, partner or role
    detail: str  # a short excerpt, so the leak can be found


def _excerpt(text: str) -> str:
    return text if len(text) <= 60 else text[:57] + "..."


def _answers(log: GameLog) -> list[tuple[str, dict[str, Any]]]:
    """Every parseable answer in the log, with the player who gave it."""
    found = []
    for call in log.calls:
        for response in call.responses:
            try:
                data = json.loads(response) if isinstance(response, str) else response
            except ValueError:
                continue
            if isinstance(data, dict):
                found.append((call.player, data))
    return found


def find_leaks(
    log: GameLog,
    prompts: Sequence[tuple[str, Sequence[Mapping[str, str]]]],
    min_length: int = 12,
    own_notes_ok: bool = False,
) -> list[Leak]:
    """Look for private texts in prompts they should never be in. Texts shorter than
    `min_length` are skipped: a short phrase could match by chance. Private notes go to nobody,
    unless `own_notes_ok` (the notes scratchpad is on): then an author may see its own."""
    roles = {p.name: p.role for p in log.players}
    wolves = {n for n, r in roles.items() if r is Role.WEREWOLF}
    seer = next((n for n, r in roles.items() if r is Role.SEER), None)

    wolf_chat = [
        e.text for e in log.events if isinstance(e, WolfChat) and len(e.text) >= min_length
    ]
    seer_lines = [
        f"You checked {e.target}: they are a {e.role.value}"
        for e in log.events
        if isinstance(e, SeerResult)
    ]
    # Said out loud, a text is public whatever else it also was: models often reuse a phrase as
    # both a private belief reason and a public vote reason.
    public = "\n".join(
        e.text if isinstance(e, Speech) else e.reason
        for e in log.events
        if isinstance(e, Speech | VoteCast)
    )
    # A player's belief reasons and summaries are its own memory, shown back to it in later
    # prompts. Several players may also write the same generic phrase. So a private text is a
    # leak only for a player who never wrote it as a belief reason or summary. Notes go to nobody,
    # not even their author, so a note never counts as "written" here.
    memory: dict[str, str] = {}
    authored: dict[str, set[str]] = {}  # player -> the notes that player wrote
    private: list[tuple[str, str]] = []  # (kind, text): notes, belief reasons, round summaries
    for owner, data in _answers(log):
        if isinstance(data.get("note"), str):
            authored.setdefault(owner, set()).add(data["note"])
        found = [("note", data.get("note")), ("summary", data.get("summary"))]
        beliefs = data.get("beliefs")
        if isinstance(beliefs, dict):
            found += [("belief", b.get("reason")) for b in beliefs.values() if isinstance(b, dict)]
        own = [t for kind, t in found if kind != "note" and isinstance(t, str)]
        memory[owner] = memory.get(owner, "") + "\n".join(own) + "\n"
        private += [(kind, t) for kind, t in found if isinstance(t, str) and len(t) >= min_length]

    leaks: dict[tuple[str, str, str], Leak] = {}

    def flag(player: str, kind: str, detail: str) -> None:
        leaks.setdefault((player, kind, detail), Leak(player, kind, _excerpt(detail)))

    for player, messages in prompts:
        system = messages[0]["content"] if messages else ""
        text = "\n".join(m["content"] for m in messages)
        if player in roles and f"you are {player}, the {roles[player].value}." not in system:
            flag(player, "role", "the system message does not state the player's own true role")
        told = re.findall(r"Your partner is (\w+),", text)
        expected = (wolves - {player}) if player in wolves else set()
        for name in told:
            if name not in expected:
                flag(player, "partner", f"told that {name} is its partner")
        if player not in wolves:
            for secret in wolf_chat:
                if secret in text:
                    flag(player, "wolf_chat", secret)
        if player != seer:
            for line in seer_lines:
                if line in text:
                    flag(player, "seer_result", line)
        mine = memory.get(player, "")
        if own_notes_ok:  # with the scratchpad or a chat, a player's own notes are its own text
            mine += "\n".join(authored.get(player, ()))
        for kind, secret in private:
            if kind == "note" and own_notes_ok and secret in authored.get(player, ()):
                continue
            # Our own fixed text (the answer examples in the system message) is not game data:
            # a model that copies an example note word for word has not leaked anything.
            if secret in text and secret not in public and secret not in mine:
                if secret not in system:
                    flag(player, kind, secret)
    return list(leaks.values())
