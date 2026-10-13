import asyncio

from werewolf.agents.scripted import policy
from werewolf.engine.actions import Agent, MemoryAction, MemoryTask, Task
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replays_exactly, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings
from werewolf.engine.views import PlayerView

SEED = 1  # Di Seer, Gus, Bo, Fay (wolf), Hal (wolf), Ada Doctor, Eve, Cy


def table() -> dict[str, Agent]:
    wolves = [p.name for p in new_game(SEED).players if p.role is Role.WEREWOLF]
    return {p.name: policy(wolves) for p in new_game(SEED).players}


def play(summarize: bool, agents: dict[str, Agent] | None = None) -> GameLog:
    settings = Settings(summarize_rounds=summarize)
    return to_log(asyncio.run(play_game(SEED, settings, agents or table())))


def memory_calls(log: GameLog) -> list[tuple[int, str]]:
    return [(c.round, c.player) for c in log.calls if c.task["kind"] == "memory"]


def test_with_the_setting_off_nobody_is_asked_for_a_summary() -> None:
    assert memory_calls(play(summarize=False)) == []


def test_the_setting_defaults_to_off_so_scripted_games_are_unchanged() -> None:
    assert Settings().summarize_rounds is False


def test_every_living_player_is_asked_once_at_the_end_of_a_round() -> None:
    # Round 1: Di is killed in the night and Fay is voted out, so six players are left.
    asked = sorted(memory_calls(play(summarize=True)))
    assert asked == sorted((1, n) for n in ("Gus", "Bo", "Hal", "Ada", "Eve", "Cy"))


def test_nobody_is_asked_after_the_game_has_ended() -> None:
    log = play(summarize=True)
    assert log.rounds == 2
    assert all(rnd < log.rounds for rnd, _ in memory_calls(log))


def test_the_dead_are_not_asked() -> None:
    names = {player for _, player in memory_calls(play(summarize=True))}
    assert "Di" not in names and "Fay" not in names


def test_the_memory_question_carries_the_length_limit() -> None:
    task = next(c.task for c in play(summarize=True).calls if c.task["kind"] == "memory")
    assert task["max_chars"] == 800


def test_the_memory_calls_are_in_the_log_and_the_game_replays_exactly() -> None:
    log = play(summarize=True)
    assert memory_calls(log)
    assert replays_exactly(log)


class LongSummary:
    """Answers the memory question with a summary over the limit; plays on as scripted."""

    def __init__(self, inner: Agent) -> None:
        self._inner = inner

    async def act(self, view: PlayerView, task: Task) -> object:
        if isinstance(task, MemoryTask):
            return MemoryAction(summary="x" * 900)
        return await self._inner.act(view, task)


def test_a_summary_over_the_limit_is_rejected_then_replaced_by_an_empty_one() -> None:
    agents = table()
    agents["Cy"] = LongSummary(agents["Cy"])
    log = play(summarize=True, agents=agents)
    cy = next(c for c in log.calls if c.player == "Cy" and c.task["kind"] == "memory")
    assert (cy.rejected, cy.failed) == (2, True)
    assert "800" in cy.errors[0]
