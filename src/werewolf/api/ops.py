"""Counters for whoever runs it, read from the database. No visitor data and no secrets."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import Connection, func, select

from werewolf.api.deps import DB, Settings
from werewolf.api.schemas import (
    AdminOverview,
    AdminPlay,
    GameCounts,
    Metrics,
    PlayCounts,
    SpendCounts,
)
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


def require_admin(config: Settings, authorization: Annotated[str | None, Header()] = None) -> None:
    """The owner only. There is no such page at all unless ADMIN_TOKEN is set, and then it needs
    `Authorization: Bearer <token>`."""
    if not config.admin_token:
        raise HTTPException(404, "Not Found")
    scheme, _, given = (authorization or "").partition(" ")
    if scheme != "Bearer" or not secrets.compare_digest(
        given.encode(), config.admin_token.encode()
    ):
        raise HTTPException(401, "A valid admin token is needed.", {"WWW-Authenticate": "Bearer"})


@router.get("/metrics", dependencies=[Depends(require_admin)])
def metrics(request: Request, db: DB) -> Metrics:
    with db.connect() as conn:
        return read_metrics(conn, request.app.state.play_day())


RECENT = 20


@router.get("/admin/overview", dependencies=[Depends(require_admin)])
def admin_overview(request: Request, db: DB, config: Settings) -> AdminOverview:
    """What the owner looks at: the counts and the latest games visitors started."""
    with db.connect() as conn:
        rows = conn.execute(
            select(play_sessions).order_by(play_sessions.c.created_at.desc()).limit(RECENT)
        ).all()
        metrics = read_metrics(conn, request.app.state.play_day())
    return AdminOverview(
        metrics=metrics,
        recent=[
            AdminPlay(
                id=r.id,
                status=r.status,
                reason=r.reason or "",
                cost=r.cost,
                created_at=r.created_at,
                game_id=r.game_id,
            )
            for r in rows
        ],
        active_games=len(request.app.state.play_tasks),
        play_model=config.play_model,
    )
