"""Strategy cards and how each did."""

from fastapi import APIRouter
from sqlalchemy import select

from werewolf.api.deps import DB, Settings
from werewolf.api.results import card_results
from werewolf.api.schemas import CardResult
from werewolf.store.tables import games
from werewolf.strategies.cards import Card, load_everywhere

router = APIRouter(tags=["cards"])


@router.get("/strategies")
def strategies(settings: Settings) -> list[Card]:
    cards = load_everywhere(settings.cards_dir)
    return sorted(cards.values(), key=lambda card: card.id)


@router.get("/results")
def results(db: DB) -> list[CardResult]:
    with db.connect() as conn:
        rows = conn.execute(select(games.c.winner, games.c.cards, games.c.rule_version))
        return [
            CardResult(**r) for r in card_results((r.winner, r.cards, r.rule_version) for r in rows)
        ]
