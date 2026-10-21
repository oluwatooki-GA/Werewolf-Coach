"""A short table manner for each player, picked from the game seed.

It changes only how a player sounds, never what it is trying to do or how much it speaks
(that is the strategy card). The same seed gives every seat the same manner in every run, so two
strategies played on one seed still face the same table. The wording is in prompts/player.yaml.
"""

from collections.abc import Sequence
from random import Random

from werewolf.prompts import load

PERSONAS: dict[str, str] = dict(load("player")["manners"])


def assign(seed: int, names: Sequence[str]) -> dict[str, str]:
    """One persona id per player, as evenly spread as eight players allow (3, 3 and 2)."""
    order = list(names)
    Random(f"persona:{seed}").shuffle(order)  # its own stream: the game's own draws are untouched
    ids = list(PERSONAS)
    return {name: ids[i % len(ids)] for i, name in enumerate(order)}


def describe(persona_id: str) -> str:
    return PERSONAS.get(persona_id, persona_id)
