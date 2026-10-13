from werewolf.engine.roles import Role, Team
from werewolf.engine.state import GameState


def winner(state: GameState, round_complete: bool) -> Team | None:
    """The village wins when the wolves are gone, or when the round limit passes with no winner.
    The wolves win when they equal or outnumber everyone else."""
    wolves = sum(p.alive and p.role is Role.WEREWOLF for p in state.players)
    others = sum(p.alive and p.role is not Role.WEREWOLF for p in state.players)
    if wolves == 0:
        return Team.VILLAGE
    if wolves >= others:
        return Team.WOLVES
    if round_complete and state.round >= state.settings.max_rounds:
        return Team.VILLAGE
    return None
