"""Games: the list and one whole replay."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from werewolf.api.deps import DB
from werewolf.api.schemas import GameDetail, GameList, GameSummary
from werewolf.engine.log import GameLog
from werewolf.store.tables import games, tags
from werewolf.tagger.derive import derive
from werewolf.tagger.tags import TagFile

router = APIRouter(tags=["games"])
SUMMARY_COLUMNS = [c for c in games.c if c.name not in ("log", "card_ids")]


@router.get("/games")
def list_games(
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    card: str | None = None,
    winner: Literal["Village", "Wolves"] | None = None,
    source: str | None = None,
    rule_version: str | None = None,
) -> GameList:
    filters = []
    if card is not None:
        filters.append(games.c.card_ids.contains(f"|{card}|", autoescape=True))
    for column, value in (
        (games.c.winner, winner),
        (games.c.source, source),
        (games.c.rule_version, rule_version),
    ):
        if value is not None:
            filters.append(column == value)
    page = (
        select(*SUMMARY_COLUMNS)
        .where(*filters)
        .order_by(games.c.seed, games.c.id)
        .limit(limit)
        .offset(offset)
    )
    with db.connect() as conn:
        total = conn.execute(select(func.count()).select_from(games).where(*filters)).scalar_one()
        rows = [GameSummary.model_validate(row._mapping) for row in conn.execute(page)]
    return GameList(total=total, games=rows)


@router.get("/games/{game_id}")
def one_game(game_id: str, db: DB) -> GameDetail:
    with db.connect() as conn:
        row = conn.execute(select(games.c.log).where(games.c.id == game_id)).first()
        if row is None:
            raise HTTPException(404, f"no game {game_id}")
        tag_row = conn.execute(select(tags.c.tagfile).where(tags.c.game_id == game_id)).first()
    log = GameLog.from_json(row.log)
    tagfile = TagFile.model_validate_json(tag_row.tagfile) if tag_row else None
    derived = derive(log, tagfile.tags) if tagfile else []
    return GameDetail(id=game_id, game=log, tags=tagfile, derived=derived)
