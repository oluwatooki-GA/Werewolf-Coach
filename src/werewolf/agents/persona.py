"""A short table manner for each player, picked from the game seed.

It changes how a player talks and how eagerly it bids for the floor, never what it is trying to do
(that is the strategy card). The same seed gives every seat the same manner in every run, so two
strategies played on one seed still face the same table.
"""

from collections.abc import Sequence
from random import Random

PERSONAS: dict[str, str] = {
    "blunt": "blunt. You say what you think in few words, ask pointed questions, and bid for the "
    "floor when you have one.",
    "chatty": "chatty. You like to talk: you speak up early and often, react to what others "
    "said, and bid high for the floor.",
    "cautious": "cautious. You listen first, speak only when you have something worth saying, "
    "and usually bid 0 or 1.",
}


def assign(seed: int, names: Sequence[str]) -> dict[str, str]:
    """One persona id per player, as evenly spread as eight players allow (3, 3 and 2)."""
    order = list(names)
    Random(f"persona:{seed}").shuffle(order)  # its own stream: the game's own draws are untouched
    ids = list(PERSONAS)
    return {name: ids[i % len(ids)] for i, name in enumerate(order)}


def describe(persona_id: str) -> str:
    return PERSONAS.get(persona_id, persona_id)
