"""Do players follow their card? Tagged moves against each card's expected moves.

Two numbers per card: the share of the player's tagged messages that contain an expected move, and
the share that match the intent the player chose when it bid. A rate comes with a 95% interval.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.strategies.cards import load_card
from werewolf.tagger.moves import ACCUSE_MOVES
from werewolf.tagger.tags import TagFile

# The moves that fit what a player said it was doing when it bid.
INTENT_MOVES = {
    "accuse": ACCUSE_MOVES,
    "ask": ("probe",),
    "defend": ("self_defend", "vouch"),
    "share_info": ("role_claim", "result_claim", "record_check"),
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for k out of n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _intents(log: GameLog) -> dict[tuple[int, str, str], str]:
    """(round, speaker, message text) -> the intent the player chose with that message."""
    found: dict[tuple[int, str, str], str] = {}
    for call in log.calls:
        if call.task.get("kind") != "bid" or call.failed or not call.responses:
            continue
        answer = call.responses[-1]
        try:
            data = json.loads(answer) if isinstance(answer, str) else answer
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("message") and data.get("intent"):
            found[(call.round, call.player, data["message"])] = data["intent"]
    return found


@dataclass
class CardStats:
    games: int = 0
    messages: int = 0
    adhering: int = 0  # messages with at least one expected move
    with_intent: int = 0  # messages posted with an intent
    intent_match: int = 0  # ... whose tag fits that intent


def adherence(games: list[tuple[GameLog, TagFile]]) -> dict[str, CardStats]:
    """Stats per card id (and model, when the log names one), over every seat that played a card."""
    stats: dict[str, CardStats] = defaultdict(CardStats)
    for log, tagfile in games:
        intents = _intents(log)
        text = {line: speech for line, speech in numbered_speeches(log.events)}
        for seat, ref in log.settings.cards.items():
            try:
                expected = set(load_card(ref).expected_moves)
            except ValueError:
                continue
            card = stats[ref.split("@")[0] + (f" on {log.model}" if log.model else "")]
            card.games += 1
            for tag in (t for t in tagfile.tags if t.speaker == seat):
                card.messages += 1
                card.adhering += bool(expected & set(tag.moves))
                speech = text.get(tag.line)
                intent = intents.get((tag.round, seat, speech.text)) if speech else None
                if intent in INTENT_MOVES:
                    card.with_intent += 1
                    card.intent_match += bool(set(INTENT_MOVES[intent]) & set(tag.moves))
    return dict(stats)


def _rate(k: int, n: int) -> str:
    if n == 0:
        return "no data"
    low, high = wilson(k, n)
    return f"{100 * k / n:.0f}% ({k}/{n}, 95% {100 * low:.0f}-{100 * high:.0f}%)"


def format_adherence(stats: dict[str, CardStats]) -> str:
    if not stats:
        return "no tagged games with cards"
    lines = []
    for card_id in sorted(stats):
        c = stats[card_id]
        lines.append(
            f"{card_id}: {c.games} seat-games, {c.messages} tagged messages\n"
            f"  follows its card: {_rate(c.adhering, c.messages)}\n"
            f"  tag matches own intent: {_rate(c.intent_match, c.with_intent)}"
        )
    return "\n".join(lines)
