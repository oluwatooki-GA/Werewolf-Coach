"""What routes ask for with `Depends(...)`: the database and the settings. Tests swap them with
`app.dependency_overrides`; routes never reach into `app.state` themselves."""

import os
from dataclasses import dataclass
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

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(web_origin=os.environ.get("WEB_ORIGIN", cls.web_origin))


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


DB = Annotated[Engine, Depends(get_engine)]
Settings = Annotated[ApiSettings, Depends(get_settings)]
