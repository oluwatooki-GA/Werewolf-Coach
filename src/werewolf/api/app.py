"""The API: builds the app from its parts. Each area is a router in its own file."""

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from werewolf.api import cards, coach, coach_runs, games, health, play
from werewolf.api.deps import ApiSettings
from werewolf.store import make_engine
from werewolf.store.play import stop_unfinished


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # a game that was running when the server stopped will never finish
    with app.state.engine.begin() as conn:
        stop_unfinished(conn, "the server restarted while this game was running")
    yield


def create_app(engine: Engine | None = None, settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    app = FastAPI(title="Werewolf Coach", lifespan=lifespan)
    app.state.engine = engine or make_engine()
    app.state.settings = settings
    app.state.play_run = play.run_visitor  # tests swap in slow or failing games
    app.state.play_tasks = set[asyncio.Task[None]]()  # games being played now
    app.state.play_day = play.today  # the day the caps count in (UTC); tests fix it
    app.state.play_clock = time.monotonic  # for the rate limit; tests move it
    app.state.play_hits = dict[str, deque[float]]()  # recent attempts by address
    app.add_middleware(
        CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["GET", "POST"]
    )
    for router in (health, games, cards, coach, coach_runs, play):
        app.include_router(router.router)
    return app
