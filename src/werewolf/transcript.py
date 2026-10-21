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


def render(log: GameLog, private: bool = False, talk_only: bool = False) -> str:
    """The public view hides roles, wolf chat, the Seer's checks and the night's real events.
    `private` shows them, plus every player's private notes. `talk_only` is always public: just
    the messages and the votes (with their outcome), under round headings."""
    roles = {p.name: p.role.value for p in log.players}
    manner = log.settings.personas
    seats = (
        ", ".join(
            f"{n}={r}"
            + (f" ({manner[n]})" if n in manner else "")
            + (f" [{log.settings.cards[n]}]" if n in log.settings.cards else "")
            for n, r in roles.items()
        )
        if private
        else ", ".join(roles)
    )
    private = private and not talk_only
    lines = (
        []
        if talk_only
        else [
            f"Game: seed {log.seed}, run {log.run_id or '-'}, {log.settings.speaking_mode.value}",
            f"Players: {seats}",
        ]
    )
    quiet: list[str] = []
    last_round = 0
    gone: dict[str, str] = {}  # who is out of the game, and how
    holder = {role: name for name, role in roles.items()}  # the Seer and the Doctor are one each

    def night_part(role: str, did: str | None, verb: str) -> str:
        """'the Seer checked Fay', or why there was no check: the Seer is already out."""
        if did:
            return f"the {role} {verb} {did}"
        name = holder.get(role)
        if name in gone:
            return f"the {role} was {gone[name]}"
        return f"the {role} {verb} nobody"

    def flush() -> None:
        if quiet:
            lines.append(f"  Listening: {', '.join(quiet)}")
            quiet.clear()

    for event in log.events:
        if talk_only and not isinstance(event, Speech | VoteCast | Removal | NoRemoval):
            continue
        if isinstance(event, Listening):
            quiet.append(event.player)
            continue
        flush()
        if event.round != last_round:
            last_round = event.round
            lines += ([""] if lines else []) + [f"=== Round {event.round} ==="]
        if isinstance(event, NightSummary):
            if private:
                saved = " (the kill was saved)" if event.saved else ""
                doctor = night_part("Doctor", event.protect, "protected")
                seer = night_part("Seer", event.check, "checked")
                lines.append(
                    f"  Night: the wolves chose {event.kill or 'nobody'}, {doctor}, {seer}{saved}"
                )
        elif isinstance(event, WolfChat):
            if private:
                lines.append(f"  [wolf chat] {event.speaker}: {event.text}")
        elif isinstance(event, SeerResult):
            if private:
                seer = event.audience[0] if event.audience else "the Seer"
                lines.append(f"  [seer] {seer} checked {event.target}: {event.role.value}")
        elif isinstance(event, Death):
            gone[event.player] = f"killed in round {event.round}"
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
            gone[event.player] = f"voted out in round {event.round}"
            lines.append(f"  {event.player} was removed by the vote.")
        elif isinstance(event, NoRemoval):
            lines.append("  Nobody was removed by the vote.")
        elif isinstance(event, GameOver):
            lines.append(f"  Game over: {event.winner.value} wins.")
    flush()
    if talk_only:
        return "\n".join(lines)

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
