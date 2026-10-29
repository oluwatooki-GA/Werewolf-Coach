"""Writing and reading finished games."""

import hashlib

from sqlalchemy import Connection, insert, select

from werewolf.engine.log import GameLog
from werewolf.store.tables import games, tags
from werewolf.tagger.tags import TagFile


def game_id(log: GameLog) -> str:
    return f"{log.seed}-{hashlib.sha256(log.to_json().encode()).hexdigest()[:8]}"


def card_ids(log: GameLog) -> str:
    """The card ids played in a game as "|a|b|" (no versions), so a query can ask for one card."""
    ids = sorted({ref.split("@")[0] for ref in log.settings.cards.values()})
    return f"|{'|'.join(ids)}|" if ids else ""


def rule_version(log: GameLog) -> str:
    """v2 is the rule set from Oct 21, 2026 (4 tokens a day, 10 turns); E1 was played on v1. v3 is
    v2 with the wolves talking in turn at night, up to a limit of messages."""
    s = log.settings
    if s.wolf_chat_messages > 0:
        return "v3"
    return "v2" if (s.tokens_per_day, s.speaking_turns) == (4, 10) else "v1"


def has_game(conn: Connection, id_: str) -> bool:
    return conn.execute(select(games.c.id).where(games.c.id == id_)).first() is not None


def add_game(
    conn: Connection,
    log: GameLog,
    *,
    source: str = "",
    status: str = "finished",
    human_seat: str | None = None,
) -> str:
    """Store a game and return its id. Storing the same log again is not an error: the id is a
    hash of the log, so a repeat is the same game."""
    id_ = game_id(log)
    if not has_game(conn, id_):
        conn.execute(
            insert(games).values(
                id=id_,
                seed=log.seed,
                winner=log.winner.value,
                rounds=log.rounds,
                model=log.model,
                cards=log.settings.cards,
                card_ids=card_ids(log),
                cost=float(log.stats.cost),
                clean=log.stats.clean,
                rule_version=rule_version(log),
                source=source,
                status=status,
                human_seat=human_seat,
                log=log.to_json(),
            )  # fmt: skip
        )
    return id_


def add_tags(conn: Connection, id_: str, tagfile: TagFile) -> bool:
    """Store a game's tags. Returns False if it already had some."""
    if conn.execute(select(tags.c.game_id).where(tags.c.game_id == id_)).first() is not None:
        return False
    conn.execute(insert(tags).values(game_id=id_, tagfile=tagfile.model_dump_json()))
    return True


def load_game(conn: Connection, id_: str) -> GameLog:
    row = conn.execute(select(games.c.log).where(games.c.id == id_)).first()
    if row is None:
        raise KeyError(id_)
    return GameLog.from_json(row.log)
