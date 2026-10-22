"""The read API: what the website shows. Starting a game is a separate part (play mode)."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, select, text

from werewolf.api.results import card_results
from werewolf.engine.log import GameLog
from werewolf.store import make_engine
from werewolf.store.tables import coach_generations, games, tags
from werewolf.strategies.cards import CARDS_DIR, load_everywhere
from werewolf.tagger.derive import derive
from werewolf.tagger.tags import TagFile

SIDES = ("wolf", "villager")
LIST_COLUMNS = [c for c in games.c if c.name != "log"]


def create_app(
    engine: Engine | None = None,
    *,
    cards_dir: Path = CARDS_DIR,
    web_origin: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Werewolf Coach")
    app.state.engine = engine or make_engine()
    origin = web_origin or os.environ.get("WEB_ORIGIN", "http://localhost:3100")
    app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=["GET"])

    @app.get("/health")
    def health() -> JSONResponse:
        try:
            with app.state.engine.connect() as conn:
                conn.execute(text("select 1"))
        except Exception:
            return JSONResponse({"status": "down", "database": "down"}, status_code=503)
        return JSONResponse({"status": "ok", "database": "ok"})

    @app.get("/games")
    def list_games(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        card: str | None = None,
        winner: Literal["Village", "Wolves"] | None = None,
        source: str | None = None,
        rule_version: str | None = None,
    ) -> dict[str, Any]:
        query = select(*LIST_COLUMNS).order_by(games.c.seed, games.c.id)
        for column, value in (
            (games.c.winner, winner),
            (games.c.source, source),
            (games.c.rule_version, rule_version),
        ):
            if value is not None:
                query = query.where(column == value)
        with app.state.engine.connect() as conn:
            rows = [dict(row._mapping) for row in conn.execute(query)]
        if card is not None:  # the card map is JSON, so this filter runs here (a few hundred rows)
            rows = [r for r in rows if card in {c.split("@")[0] for c in r["cards"].values()}]
        return {"total": len(rows), "games": rows[offset : offset + limit]}

    @app.get("/games/{game_id}")
    def one_game(game_id: str) -> dict[str, Any]:
        with app.state.engine.connect() as conn:
            row = conn.execute(select(games.c.log).where(games.c.id == game_id)).first()
            if row is None:
                raise HTTPException(404, f"no game {game_id}")
            tag_row = conn.execute(select(tags.c.tagfile).where(tags.c.game_id == game_id)).first()
        log = GameLog.from_json(row.log)
        tagfile = TagFile.model_validate_json(tag_row.tagfile) if tag_row else None
        derived = derive(log, tagfile.tags) if tagfile else []
        return {
            "id": game_id,
            "game": json.loads(row.log),
            "tags": tagfile.model_dump(mode="json") if tagfile else None,
            "derived": [d.model_dump(mode="json") for d in derived],
        }

    @app.get("/strategies")
    def strategies() -> list[dict[str, Any]]:
        cards = load_everywhere(cards_dir)
        return [c.model_dump(mode="json") for c in sorted(cards.values(), key=lambda c: c.id)]

    @app.get("/results")
    def results() -> list[dict[str, Any]]:
        with app.state.engine.connect() as conn:
            rows = conn.execute(select(games.c.winner, games.c.cards, games.c.rule_version))
            return card_results((r.winner, r.cards, r.rule_version) for r in rows)

    @app.get("/coach/{side}")
    def coach(side: str) -> dict[str, Any]:
        if side not in SIDES:
            raise HTTPException(404, f"no side {side}; use one of: {', '.join(SIDES)}")
        query = (
            select(coach_generations.c.record)
            .where(coach_generations.c.side == side)
            .order_by(coach_generations.c.number)
        )
        with app.state.engine.connect() as conn:
            records = [json.loads(row.record) for row in conn.execute(query)]
        return {"side": side, "generations": records}

    return app
