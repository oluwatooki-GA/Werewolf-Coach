"""Is the service up, and is play mode able to play? Never makes a paid call."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from werewolf.api.deps import DB, Settings
from werewolf.api.play import current_verdict
from werewolf.api.schemas import Health
from werewolf.llm.faults import active_faults
from werewolf.llm.transport import LiteLLMTransport
from werewolf.runtime import KEY_FOR

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=Health)
def health(request: Request, db: DB, config: Settings) -> JSONResponse:
    try:
        with db.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:  # any failure to reach the database means "down"
        return JSONResponse(Health(status="down", database="down").model_dump(), status_code=503)
    model = config.play_model
    provider: str = "off"
    play: str = "off"
    if model:
        play = "paused" if current_verdict(request, db, config).state == "paused" else "open"
        key = None if model == "fake" else KEY_FOR.get(LiteLLMTransport().provider(model))
        if key is not None:  # free scripted games have no provider to check
            provider = "ok" if os.environ.get(key) else "missing_key"
    status = "degraded" if provider == "missing_key" else "ok"
    body = Health(
        status=status,
        database="ok",
        provider=provider,
        play=play,
        active_games=len(request.app.state.play_tasks),
        faults=active_faults(),
    )
    return JSONResponse(body.model_dump())
