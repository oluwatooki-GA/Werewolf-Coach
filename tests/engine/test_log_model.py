"""The log can name the model that played; a log without one keeps its exact old bytes."""

import asyncio
import json

from werewolf.agents.scripted import policy
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replays_exactly, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game


def played(model: str) -> GameLog:
    players = new_game(1).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    state = asyncio.run(play_game(1, None, {p.name: policy(wolves) for p in players}))
    return to_log(state, model=model)


def test_a_log_without_a_model_has_no_model_key() -> None:
    assert "model" not in json.loads(played("").to_json())


def test_the_model_round_trips_and_a_named_log_replays_exactly() -> None:
    log = played("gpt-4.1-nano")
    assert json.loads(log.to_json())["model"] == "gpt-4.1-nano"
    again = GameLog.from_json(log.to_json())
    assert again.model == "gpt-4.1-nano" and replays_exactly(again)
