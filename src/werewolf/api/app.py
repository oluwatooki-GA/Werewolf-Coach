"""The API: builds the app from its parts. Each area is a router in its own file."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from werewolf.api import cards, coach, coach_runs, games, health, play
from werewolf.api.deps import ApiSettings
from werewolf.store import make_engine


def create_app(engine: Engine | None = None, settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    app = FastAPI(title="Werewolf Coach")
    app.state.engine = engine or make_engine()
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["GET"])
    for router in (health, games, cards, coach, coach_runs, play):
        app.include_router(router.router)
    return app
