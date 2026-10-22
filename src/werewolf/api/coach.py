"""The coach's history, read from the database.

Starting a coach run from the API is not built: see `coach_runs.py`.
"""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from werewolf.api.deps import DB
from werewolf.api.schemas import CoachHistory
from werewolf.coach.evidence import SIDES
from werewolf.coach.history import Generation
from werewolf.store.tables import coach_generations

router = APIRouter(tags=["coach"])


@router.get("/coach/{side}")
def coach(side: str, db: DB) -> CoachHistory:
    if side not in SIDES:
        raise HTTPException(404, f"no side {side}; use one of: {', '.join(SIDES)}")
    query = (
        select(coach_generations.c.record)
        .where(coach_generations.c.side == side)
        .order_by(coach_generations.c.number)
    )
    with db.connect() as conn:
        generations = [Generation.model_validate_json(row.record) for row in conn.execute(query)]
    return CoachHistory(side=cast(Literal["wolf", "villager"], side), generations=generations)
