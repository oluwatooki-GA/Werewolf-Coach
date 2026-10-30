"""Counters for whoever runs it, read from the database. No visitor data and no secrets."""

from fastapi import APIRouter, Request
from sqlalchemy import Connection, func, select

from werewolf.api.deps import DB
from werewolf.api.schemas import GameCounts, Metrics, PlayCounts, SpendCounts
from werewolf.store.tables import games, play_sessions, play_spend

router = APIRouter(tags=["ops"])


def _counts(conn: Connection, column) -> dict[str, int]:  # type: ignore[no-untyped-def]
    rows = conn.execute(select(column, func.count()).group_by(column)).all()
    return {str(key): int(n) for key, n in rows}


def read_metrics(conn: Connection, today: str) -> Metrics:
    plays = _counts(conn, play_sessions.c.status)
    by_day = {
        r.day: float(r.spent) for r in conn.execute(select(play_spend).order_by(play_spend.c.day))
    }
    return Metrics(
        games=GameCounts(
            total=conn.execute(select(func.count()).select_from(games)).scalar_one(),
            by_status=_counts(conn, games.c.status),
            by_source=_counts(conn, games.c.source),
            unclean=conn.execute(
                select(func.count()).select_from(games).where(games.c.clean.is_(False))
            ).scalar_one(),
        ),
        play=PlayCounts(
            started=sum(plays.values()),
            finished=plays.get("finished", 0),
            stopped=plays.get("stopped", 0),
            running=plays.get("running", 0),
        ),
        spend=SpendCounts(today=by_day.get(today, 0.0), total=sum(by_day.values()), by_day=by_day),
    )


@router.get("/metrics")
def metrics(request: Request, db: DB) -> Metrics:
    with db.connect() as conn:
        return read_metrics(conn, request.app.state.play_day())
