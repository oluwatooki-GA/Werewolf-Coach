"""What routes ask for with `Depends(...)`: the database and the settings. Tests swap them with
`app.dependency_overrides`; routes never reach into `app.state` themselves."""

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine

from werewolf.strategies.cards import CARDS_DIR


@dataclass(frozen=True)
class ApiSettings:
    """Everything the API reads from its environment, read once when the app is built."""

    web_origin: str = "http://localhost:3100"  # the one site allowed to call the API
    cards_dir: Path = CARDS_DIR
    # Play mode. Empty means it is not set up, so a server nobody configured spends nothing.
    # "fake" plays free scripted games; any other value is the model the AI seats use.
    play_model: str = ""
    play_max_games: int = 2  # games being played at once, in all
    play_game_budget: Decimal = Decimal("0.40")  # dollars one game may spend
    play_game_estimate: Decimal = Decimal("0.30")  # what a game is assumed to cost, for the caps
    play_daily_cap: Decimal = Decimal("1.00")  # dollars a day, all visitors together
    play_total_cap: Decimal = Decimal("10.00")  # dollars in all
    play_requests_per_minute: int = 10  # starts a single address may attempt in a minute
    admin_token: str = ""  # empty: there is no admin page at all

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            web_origin=os.environ.get("WEB_ORIGIN", cls.web_origin),
            play_model=os.environ.get("PLAY_MODEL", cls.play_model),
            play_game_budget=Decimal(os.environ.get("PLAY_GAME_BUDGET", cls.play_game_budget)),
            play_game_estimate=Decimal(
                os.environ.get("PLAY_GAME_ESTIMATE", cls.play_game_estimate)
            ),
            play_daily_cap=Decimal(os.environ.get("PLAY_DAILY_CAP", cls.play_daily_cap)),
            play_total_cap=Decimal(os.environ.get("PLAY_TOTAL_CAP", cls.play_total_cap)),
            play_requests_per_minute=int(
                os.environ.get("PLAY_REQUESTS_PER_MINUTE", cls.play_requests_per_minute)
            ),
            admin_token=os.environ.get("ADMIN_TOKEN", cls.admin_token),
        )


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


DB = Annotated[Engine, Depends(get_engine)]
Settings = Annotated[ApiSettings, Depends(get_settings)]
