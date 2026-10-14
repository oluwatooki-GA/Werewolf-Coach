"""Facts the game writes down for itself: numbered lines, cite checks, and the round record.

Everything here is computed from the public events only, so every player gets the same text.
Opinions stay with the model; this is what the log can prove.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence

from werewolf.engine.events import (
    Cite,
    Death,
    Event,
    NoDeath,
    NoRemoval,
    Removal,
    Speech,
    VoteCast,
)
from werewolf.engine.roles import Role


def numbered_speeches(events: Iterable[Event]) -> list[tuple[str, Speech]]:
    """Every public message with its line number: "R2-4" is the 4th message of round 2."""
    counts: Counter[int] = Counter()
    found = []
    for event in events:
        if isinstance(event, Speech) and event.audience is None:
            counts[event.round] += 1
            found.append((f"R{event.round}-{counts[event.round]}", event))
    return found


def check_cites(
    cites: Sequence[Cite], events: Iterable[Event]
) -> tuple[tuple[Cite, ...], tuple[str, ...]]:
    """Tidy a message's cites and find the invented ones: no such line, or a different speaker.
    Returns (the cites without repeats, the lines that were invented)."""
    real = {line: speech.speaker for line, speech in numbered_speeches(events)}
    tidy = tuple(
        dict.fromkeys(
            Cite(line=c.line.strip().strip("[]").strip().upper(), speaker=c.speaker.strip())
            for c in cites
        )
    )
    return tidy, tuple(c.line for c in tidy if real.get(c.line) != c.speaker)


_ROLE_WORDS = {
    "seer": Role.SEER,
    "doctor": Role.DOCTOR,
    "villager": Role.VILLAGER,
    "werewolf": Role.WEREWOLF,
    "wolf": Role.WEREWOLF,
}
_ROLE = r"(seer|doctor|villager|werewolf|wolf)\b"
_FILLER = r"(?:(?:the|a|an|just|only|plain|real|actual|simple|regular)\s+)*"
_I_AM = r"(?:i am|i['’]m|im)"
_SELF = re.compile(rf"(?<!\bif )\b{_I_AM}\s+{_FILLER}{_ROLE}", re.IGNORECASE)


def claimed_roles(speaker: str, text: str) -> list[Role]:
    """Roles a message says its own speaker has: "I am the Doctor", "Hal here, plain villager".
    Careful rather than complete (it reads the plain first-person forms and nothing cleverer)."""
    name = re.escape(speaker)
    here = re.compile(
        rf"\b(?:{name}\s+here|{_I_AM}\s+{name}),?\s+(?:as\s+)?{_FILLER}{_ROLE}",
        re.IGNORECASE,
    )
    found = [m.group(1) for m in (*_SELF.finditer(text), *here.finditer(text))]
    return list(dict.fromkeys(_ROLE_WORDS[word.lower()] for word in found))


def round_record(events: Iterable[Event], round_: int) -> str:
    """One line of fact about a finished round: deaths, role claims, who voted for whom, and
    who was removed."""
    events = list(events)
    public = [e for e in events if e.round == round_ and e.audience is None]
    parts = []

    died = [e.player for e in public if isinstance(e, Death)]
    if died:
        parts.append(f"died in the night: {', '.join(died)}")
    elif any(isinstance(e, NoDeath) for e in public):
        parts.append("nobody died in the night")

    claims: dict[tuple[str, Role], str] = {}
    for line, speech in numbered_speeches(events):
        if speech.round == round_:
            for role in claimed_roles(speech.speaker, speech.text):
                claims.setdefault((speech.speaker, role), line)
    if claims:
        shown = ", ".join(f"{who} {role.value} ({line})" for (who, role), line in claims.items())
        parts.append(f"claimed a role: {shown}")

    ballots = [e for e in public if isinstance(e, VoteCast)]
    tally: dict[str, list[str]] = {}
    for vote in ballots:
        if vote.target is not None:
            tally.setdefault(vote.target, []).append(vote.voter)
    if tally:
        ranked = sorted(tally.items(), key=lambda item: -len(item[1]))  # ties keep the vote order
        parts.append("votes: " + "; ".join(f"{t} {len(v)} ({', '.join(v)})" for t, v in ranked))
    away = [v.voter for v in ballots if v.target is None]
    if away:
        parts.append(f"abstained: {', '.join(away)}")

    removed = [e.player for e in public if isinstance(e, Removal)]
    if removed:
        parts.append(f"removed by the vote: {', '.join(removed)}")
    elif any(isinstance(e, NoRemoval) for e in public):
        parts.append("nobody was removed by the vote")
    return f"Round {round_}: " + "; ".join(parts) + "." if parts else f"Round {round_}: nothing."
