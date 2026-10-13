import random

from werewolf.engine.roles import ROLE_DECK
from werewolf.engine.state import GameState, Player, Settings


def new_game(seed: int, settings: Settings | None = None) -> GameState:
    """Deal seats and roles from the seed. The draw order is fixed: seats, then roles."""
    settings = settings or Settings()
    rng = random.Random(seed)
    seats = list(settings.names)
    roles = list(ROLE_DECK)
    rng.shuffle(seats)
    rng.shuffle(roles)
    players = [Player(name, role) for name, role in zip(seats, roles, strict=True)]
    return GameState(seed=seed, settings=settings, players=players, rng=rng)
