"""Play sessions: one row per game a visitor started, `running` until `finished` or `stopped`."""

import time
import uuid
from collections.abc import Mapping

from sqlalchemy import Connection, Row, insert, select, update

from werewolf.store.tables import play_sessions


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
