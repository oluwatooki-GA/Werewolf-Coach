"""A saved game as readable text: what a watcher sees, or (private) what really went on."""

import json

from werewolf.engine.events import (
    Death,
    GameOver,
    Listening,
    NightSummary,
    NoDeath,
    NoRemoval,
    Removal,
    SeerResult,
    Speech,
    VoteCast,
    WolfChat,
)
from werewolf.engine.log import GameLog


def _tokens(n: int) -> str:
    return f"{n} token" if n == 1 else f"{n} tokens"


def _notes(log: GameLog) -> list[str]:
    """Every private note and round summary the players wrote, in the order they were asked."""
    lines = []
    for call in log.calls:
        for response in call.responses:
            try:
                data = json.loads(response) if isinstance(response, str) else response
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            for field in ("note", "summary"):
                text = data.get(field)
                if isinstance(text, str) and text.strip():
                    kind = call.task["kind"]
                    lines.append(f"  round {call.round}, {call.player} ({kind}, {field}): {text}")
    return lines


def render(log: GameLog, private: bool = False) -> str:
    """The public view hides roles, wolf chat, the Seer's checks and the night's real events.
    `private` shows them, plus every player's private notes."""
    roles = {p.name: p.role.value for p in log.players}
    seats = ", ".join(f"{n}={r}" for n, r in roles.items()) if private else ", ".join(roles)
    lines = [
        f"Game: seed {log.seed}, run {log.run_id or '-'}, {log.settings.speaking_mode.value}",
        f"Players: {seats}",
    ]
    quiet: list[str] = []
    last_round = 0

    def flush() -> None:
        if quiet:
            lines.append(f"  Listening: {', '.join(quiet)}")
            quiet.clear()

    for event in log.events:
        if isinstance(event, Listening):
            quiet.append(event.player)
            continue
        flush()
        if event.round != last_round:
            last_round = event.round
            lines += ["", f"=== Round {event.round} ==="]
        if isinstance(event, NightSummary):
            if private:
                saved = " (the kill was saved)" if event.saved else ""
                kill, protect = event.kill or "nobody", event.protect or "nobody"
                check = event.check or "nobody"
                lines.append(
                    f"  Night: the wolves chose {kill}, the Doctor protected {protect}, "
                    f"the Seer checked {check}{saved}"
                )
        elif isinstance(event, WolfChat):
            if private:
                lines.append(f"  [wolf chat] {event.speaker}: {event.text}")
        elif isinstance(event, SeerResult):
            if private:
                seer = event.audience[0] if event.audience else "the Seer"
                lines.append(f"  [seer] {seer} checked {event.target}: {event.role.value}")
        elif isinstance(event, Death):
            lines.append(f"  Morning: {event.player} was killed in the night.")
        elif isinstance(event, NoDeath):
            lines.append("  Morning: nobody died in the night.")
        elif isinstance(event, Speech):
            if event.reply:
                lines.append(f"  {event.speaker} replies (free): {event.text}")
            elif event.paid:
                lines.append(f"  {event.speaker} says ({_tokens(event.paid)}): {event.text}")
            else:
                lines.append(f"  {event.speaker} says: {event.text}")
        elif isinstance(event, VoteCast):
            if event.target is None:
                lines.append(f"  Vote: {event.voter} abstained.")
            else:
                why = f" (reason: {event.reason})" if event.reason else ""
                lines.append(f"  Vote: {event.voter} voted for {event.target}{why}.")
        elif isinstance(event, Removal):
            lines.append(f"  {event.player} was removed by the vote.")
        elif isinstance(event, NoRemoval):
            lines.append("  Nobody was removed by the vote.")
        elif isinstance(event, GameOver):
            lines.append(f"  Game over: {event.winner.value} wins.")
    flush()

    s = log.stats
    lines += [
        "",
        f"{len(log.calls)} calls, rejected {s.rejected} of {s.responses} answers, "
        f"fallbacks {s.failed_calls}, cost ${s.cost:.6f}",
    ]
    if private:
        notes = _notes(log)
        if notes:
            lines += ["", "Private notes and summaries:", *notes]
    return "\n".join(lines)
