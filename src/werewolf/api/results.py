"""Win rates per strategy card, worked out from the stored games."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from werewolf.engine.roles import Role, Team
from werewolf.strategies.cards import ROLE_FOR_PREFIX
from werewolf.tagger.adherence import wilson

ENOUGH_GAMES = 10  # under this the gap between two cards is "not clear yet" (DESIGN 6.1)


def card_results(games: Iterable[tuple[str, Mapping[str, str], str]]) -> list[dict[str, Any]]:
    """One row per card version and rule version. `games` is (winner, seat -> card ref, rule
    version). A game counts once for a card however many seats played it, and a win is the card's
    team winning (wolf cards for the wolves, every other card for the village)."""
    played: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for winner, cards, rule_version in games:
        for ref in set(cards.values()):
            role = ROLE_FOR_PREFIX[ref.split(".")[0]]
            team = Team.WOLVES if role is Role.WEREWOLF else Team.VILLAGE
            tally = played[(ref, rule_version)]
            tally[0] += 1
            tally[1] += winner == team.value
    rows = []
    for (ref, rule_version), (n, wins) in played.items():
        low, high = wilson(wins, n)
        rows.append(
            {
                "card": ref,
                "role": ROLE_FOR_PREFIX[ref.split(".")[0]].value,
                "rule_version": rule_version,
                "games": n,
                "wins": wins,
                "rate": wins / n,
                "low": low,
                "high": high,
                "enough": n >= ENOUGH_GAMES,
            }
        )
    return sorted(rows, key=lambda r: (r["role"], r["rule_version"], -r["rate"], r["card"]))
