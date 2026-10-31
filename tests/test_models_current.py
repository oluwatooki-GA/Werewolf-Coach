"""The models this project defaults to are priced and not retired, so a default never breaks."""

from datetime import date

import litellm

from werewolf.llm.types import CHEAP_MODEL


def test_the_cheap_default_model_is_priced_and_not_retired() -> None:
    info = litellm.model_cost[CHEAP_MODEL]
    assert info["input_cost_per_token"] > 0 and info["output_cost_per_token"] > 0
    retired = info.get("deprecation_date")
    assert retired is None or date.fromisoformat(retired) > date.today(), (
        f"{CHEAP_MODEL} is retired"
    )


def test_it_is_the_model_play_runs_on() -> None:
    assert CHEAP_MODEL == "gpt-4o-mini"
