"""What the coach reads: the games a side lost, as short digests with the names taken out, plus
counts across all the games that card played.

The coach is an analyst. It sees roles, moves, votes and the side's private notes, because it reads
the games after they are over. The card it writes may use none of that: a card is advice for a
role, so names are replaced by roles here and the card check bans names.
"""

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from werewolf.engine.events import Death, Removal, VoteCast, WolfChat
from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.engine.roles import Role, Team
from werewolf.tagger.derive import derive
from werewolf.tagger.moves import ACCUSE_MOVES
from werewolf.tagger.tags import TagFile

SIDES: dict[str, tuple[Role, Team]] = {
    "wolf": (Role.WEREWOLF, Team.WOLVES),
    "villager": (Role.VILLAGER, Team.VILLAGE),
}
MAX_MESSAGES = 14  # side messages shown for one game
MAX_NOTES = 6
MAX_CHAT = 4
NOTE_CHARS = 120
MESSAGE_CHARS = 200


@dataclass(frozen=True)
class Evidence:
    side: str
    card_id: str | None
    games: int  # games given (after the card filter)
    lost: int  # of those, games the side lost
    used: int  # digests included in the text
    left_out: int  # lost games that did not fit
    text: str

    @property
    def empty(self) -> bool:
        return self.used == 0


def _labels(log: GameLog) -> dict[str, str]:
    """Each player's anonymous label: Wolf A, Wolf B, Seer, Doctor, Villager 1 to 4."""
    labels: dict[str, str] = {}
    counts: dict[Role, int] = defaultdict(int)
    for player in log.players:
        counts[player.role] += 1
        n = counts[player.role]
        if player.role is Role.WEREWOLF:
            labels[player.name] = f"Wolf {'AB'[n - 1]}"
        elif player.role is Role.VILLAGER:
            labels[player.name] = f"Villager {n}"
        else:
            labels[player.name] = player.role.value
    return labels


def _hide_names(text: str, labels: dict[str, str]) -> str:
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in labels) + r")\b")
    return pattern.sub(lambda m: labels[m.group(1)], text)


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _notes(log: GameLog, seats: set[str], labels: dict[str, str]) -> list[str]:
    found = []
    for call in log.calls:
        if call.player not in seats or call.task.get("kind") != "vote" or not call.responses:
            continue
        try:
            answer = call.responses[-1]
            data = json.loads(answer) if isinstance(answer, str) else answer
            note = str(data.get("note", "")).strip()
        except (ValueError, AttributeError):
            continue
        if note:
            who = labels[call.player]
            found.append(
                f"{who} (round {call.round}): {_hide_names(_cut(note, NOTE_CHARS), labels)}"
            )
    return found[:MAX_NOTES]


def _digest(
    number: int, log: GameLog, tagfile: TagFile | None, seats: set[str], wolf_side: bool
) -> str:
    labels = _labels(log)
    tagged = {t.line: t for t in tagfile.tags} if tagfile else {}
    shown: dict[str, list[str]] = {}
    if tagfile:
        for d in derive(log, tagfile.tags):
            if d.line and d.speaker in seats:
                shown.setdefault(d.line, []).append(d.label)
    lines = [f"Game {number}: lost in round {log.rounds}."]
    for event in log.events:
        if isinstance(event, Removal):
            lines.append(f"  Round {event.round}: {labels[event.player]} was voted out.")
        elif isinstance(event, Death):
            lines.append(f"  Round {event.round}: {labels[event.player]} was killed at night.")
    mine = [(ln, s) for ln, s in numbered_speeches(log.events) if s.speaker in seats]
    lines.append(f"  The side's messages ({len(mine)}):" + ("" if tagfile else " (not tagged)"))
    for line, speech in mine[:MAX_MESSAGES]:
        tag = tagged.get(line)
        moves = ""
        if tag:
            target = f" -> {labels[tag.target]}" if tag.target in labels else ""
            moves = f"({'+'.join(tag.moves)}{target}) "
        extra = f" [{', '.join(shown[line])}]" if line in shown else ""
        text = _hide_names(_cut(speech.text, MESSAGE_CHARS), labels)
        lines.append(f"    [{line}] {labels[speech.speaker]} {moves}{text}{extra}")
    if len(mine) > MAX_MESSAGES:
        lines.append(f"    (+{len(mine) - MAX_MESSAGES} more messages)")
    votes = [e for e in log.events if isinstance(e, VoteCast) and e.target is not None]
    mine_votes = [v for v in votes if v.voter in seats or v.target in seats]
    if mine_votes:
        lines.append("  Votes involving the side:")
        for v in mine_votes:
            why = _hide_names(_cut(v.reason, 80), labels)
            lines.append(
                f"    Round {v.round}: {labels[v.voter]} -> {labels[str(v.target)]}"
                + (f" ({why})" if why else "")
            )
    notes = _notes(log, seats, labels)
    if notes:
        lines.append("  Private notes of the side:")
        lines += [f"    {n}" for n in notes]
    if wolf_side:
        chat = [e for e in log.events if isinstance(e, WolfChat)][:MAX_CHAT]
        if chat:
            lines.append("  Wolf chat:")
            lines += [
                f"    {labels[c.speaker]}: {_hide_names(_cut(c.text, MESSAGE_CHARS), labels)}"
                for c in chat
            ]
    return "\n".join(lines)


def _accused_round_one(log: GameLog, tagfile: TagFile | None, seat: str) -> bool:
    if tagfile is None:
        return False
    return any(
        t.speaker == seat and t.round == 1 and any(m in ACCUSE_MOVES for m in t.moves)
        for t in tagfile.tags
    )


def _voted_out_by(log: GameLog, seat: str, round_: int) -> bool:
    return any(
        isinstance(e, Removal) and e.player == seat and e.round <= round_ for e in log.events
    )


def _aggregate(
    games: Sequence[tuple[GameLog, TagFile | None]], role: Role, team: Team, side: str
) -> str:
    seat_games = accused = accused_out = quiet = quiet_out = won = 0
    for log, tagfile in games:
        won += log.winner is team
        for player in (p for p in log.players if p.role is role):
            seat_games += 1
            out = _voted_out_by(log, player.name, 2)
            if _accused_round_one(log, tagfile, player.name):
                accused += 1
                accused_out += out
            else:
                quiet += 1
                quiet_out += out
    n = len(games)
    return "\n".join(
        [
            f"Across all {n} games with this card the {side} side won {won} ({n - won} lost).",
            f"{side} seats that accused in round 1: {accused} of {seat_games} seat-games; "
            f"of those, voted out by the end of round 2: {accused_out} of {accused}.",
            f"{side} seats that did not accuse in round 1: voted out by the end of round 2: "
            f"{quiet_out} of {quiet}.",
        ]
    )


def build_evidence(
    games: Sequence[tuple[GameLog, TagFile | None]],
    side: str,
    card_id: str | None = None,
    max_chars: int = 12000,
) -> Evidence:
    """Digests of the lost games of one side. `card_id` keeps only games where the side's seats
    played that card. The size limit applies to the digests; the counts are always included."""
    role, team = SIDES[side]
    if card_id:
        games = [
            (log, tags)
            for log, tags in games
            if any(
                ref.split("@")[0] == card_id
                for seat, ref in log.settings.cards.items()
                if any(p.name == seat and p.role is role for p in log.players)
            )
        ]
    lost = sorted((g for g in games if g[0].winner is not team), key=lambda g: g[0].rounds)
    if not lost:
        text = (
            f"There is nothing to learn from: the {side} side won every one of the "
            f"{len(games)} games."
        )
        return Evidence(side, card_id, len(games), 0, 0, 0, text)
    header = _aggregate(games, role, team, side)
    budget = max_chars
    digests: list[str] = []
    for number, (log, tagfile) in enumerate(lost, start=1):
        seats = {p.name for p in log.players if p.role is role}
        digest = _digest(number, log, tagfile, seats, side == "wolf")
        if digests and len(digest) > budget:
            break
        digests.append(digest if digests else _cut_lines(digest, budget))
        budget -= len(digest)
    left_out = len(lost) - len(digests)
    body = "\n\n".join(digests)
    tail = (
        f"\n\n({left_out} more lost games were left out to fit the size limit.)" if left_out else ""
    )
    return Evidence(
        side, card_id, len(games), len(lost), len(digests), left_out, f"{header}\n\n{body}{tail}"
    )


def _cut_lines(digest: str, limit: int) -> str:
    """Keep the first game whole if it fits, else its first lines, so the coach reads something."""
    if len(digest) <= limit:
        return digest
    kept, size = [], 0
    for line in digest.splitlines():
        if size + len(line) + 1 > limit:
            break
        kept.append(line)
        size += len(line) + 1
    return "\n".join(kept)
