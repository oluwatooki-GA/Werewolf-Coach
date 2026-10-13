"""Leak audit: check the prompts a game actually sent against the secrets in its log.

Used by the CI leak test (planted code words) and by real runs (the game's own private texts).
It lives outside `agents/` because it reads the log, which holds every secret.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from werewolf.engine.events import SeerResult, WolfChat
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
) -> list[Leak]:
    """Look for private texts in prompts they should never be in. Texts shorter than
    `min_length` are skipped: a short phrase could match by chance."""
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
    notes: list[str] = []
    reasons: list[tuple[str, str]] = []  # (owner, reason)
    summaries: list[tuple[str, str]] = []  # (owner, round summary)
    for owner, data in _answers(log):
        note = data.get("note")
        if isinstance(note, str) and len(note) >= min_length:
            notes.append(note)
        summary = data.get("summary")
        if isinstance(summary, str) and len(summary) >= min_length:
            summaries.append((owner, summary))
        beliefs = data.get("beliefs")
        if isinstance(beliefs, dict):
            for belief in beliefs.values():
                reason = belief.get("reason") if isinstance(belief, dict) else None
                if isinstance(reason, str) and len(reason) >= min_length:
                    reasons.append((owner, reason))

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
        for secret in notes:
            if secret in text:
                flag(player, "note", secret)
        for owner, reason in reasons:
            if owner != player and reason in text:
                flag(player, "belief", reason)
        for owner, summary in summaries:
            if owner != player and summary in text:
                flag(player, "summary", summary)
    return list(leaks.values())
