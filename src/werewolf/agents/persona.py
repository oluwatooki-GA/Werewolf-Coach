"""A short table manner for each player, picked from the game seed.

It changes only how a player sounds, never what it is trying to do or how much it speaks
(that is the strategy card). The same seed gives every seat the same manner in every run, so two
strategies played on one seed still face the same table.
"""

from collections.abc import Sequence
from random import Random

PERSONAS: dict[str, str] = {
    "blunt": "blunt. You say what you think in few words and ask pointed questions.",
    "chatty": "chatty. You write warmly and at some length, and react to what others said.",
    "cautious": "cautious. You hedge, qualify what you say, and avoid strong statements.",
}


def assign(seed: int, names: Sequence[str]) -> dict[str, str]:
    """One persona id per player, as evenly spread as eight players allow (3, 3 and 2)."""
    order = list(names)
    Random(f"persona:{seed}").shuffle(order)  # its own stream: the game's own draws are untouched
    ids = list(PERSONAS)
    return {name: ids[i % len(ids)] for i, name in enumerate(order)}


def describe(persona_id: str) -> str:
    return PERSONAS.get(persona_id, persona_id)
