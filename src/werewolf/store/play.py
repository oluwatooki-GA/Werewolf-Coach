"""Play sessions: one row per game a visitor started, `running` until `finished` or `stopped`."""

import time
import uuid
from collections.abc import Mapping

from sqlalchemy import Connection, Row, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from werewolf.store.tables import play_sessions, play_spend


def new_session(conn: Connection, picks: Mapping[str, str]) -> str:
    """Record that a game has started, with the cards that were picked. Returns its id."""
    id_ = uuid.uuid4().hex
    conn.execute(
        insert(play_sessions).values(
            id=id_,
            status="running",
            game_id=None,
            reason="",
            cards=dict(picks),
            cost=0.0,
            created_at=time.time(),
        )  # fmt: skip
    )
    return id_


def finish_session(
    conn: Connection,
    id_: str,
    status: str,
    *,
    game_id: str | None = None,
    reason: str = "",
    cost: float = 0.0,
) -> None:
    conn.execute(
        update(play_sessions)
        .where(play_sessions.c.id == id_)
        .values(status=status, game_id=game_id, reason=reason, cost=cost)
    )


def get_session(conn: Connection, id_: str) -> Row | None:  # type: ignore[type-arg]
    return conn.execute(select(play_sessions).where(play_sessions.c.id == id_)).first()


def stop_unfinished(conn: Connection, reason: str) -> int:
    """Games that were running when the server stopped will never finish: mark them stopped."""
    result = conn.execute(
        update(play_sessions)
        .where(play_sessions.c.status == "running")
        .values(status="stopped", reason=reason)
    )
    return result.rowcount


def add_spend(conn: Connection, day: str, amount: float) -> None:
    """Add what a game cost to that day's total, starting the day's row if it has none."""
    bump = (
        update(play_spend).where(play_spend.c.day == day).values(spent=play_spend.c.spent + amount)
    )
    if conn.execute(bump).rowcount:
        return
    try:
        with conn.begin_nested():  # two games finishing together may both try to start the row
            conn.execute(insert(play_spend).values(day=day, spent=amount))
    except IntegrityError:
        conn.execute(bump)


def spent_today(conn: Connection, day: str) -> float:
    row = conn.execute(select(play_spend.c.spent).where(play_spend.c.day == day)).first()
    return float(row.spent) if row else 0.0


def spent_total(conn: Connection) -> float:
    return float(
        conn.execute(select(func.coalesce(func.sum(play_spend.c.spent), 0.0))).scalar_one()
    )
