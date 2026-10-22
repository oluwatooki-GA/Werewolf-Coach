"""Is the service up? T11 adds the provider check, the game counts and /metrics."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from werewolf.api.deps import DB
from werewolf.api.schemas import Health

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=Health)
def health(db: DB) -> JSONResponse:
    try:
        with db.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:  # any failure to reach the database means "down"
        return JSONResponse(Health(status="down", database="down").model_dump(), status_code=503)
    return JSONResponse(Health(status="ok", database="ok").model_dump())
