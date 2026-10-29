"""What the API sends back. These models are the contract the website is written against: they
show up in `/docs` and in `/openapi.json`, and FastAPI checks every answer against them."""

from typing import Literal

from pydantic import BaseModel

from werewolf.coach.history import Generation
from werewolf.engine.log import GameLog
from werewolf.tagger.tags import DerivedTag, TagFile


class Health(BaseModel):
    status: Literal["ok", "down"]
    database: Literal["ok", "down"]


class GameSummary(BaseModel):
    """One row of the games list: everything except the log itself."""

    id: str
    seed: int
    winner: Literal["Village", "Wolves"]
    rounds: int
    model: str
    cards: dict[str, str]  # seat -> "id@version"
    cost: float
    clean: bool
    rule_version: str
    source: str
    status: str
    human_seat: str | None


class GameList(BaseModel):
    total: int
    games: list[GameSummary]


class Featured(BaseModel):
    """The moment the site opens on: a game and the line in it to show."""

    game_id: str
    focus: str  # a line number such as "R1-3"


class GameDetail(BaseModel):
    id: str
    game: GameLog
    tags: TagFile | None
    derived: list[DerivedTag]


class CardResult(BaseModel):
    """How one card version did in the stored games, under one rule version."""

    card: str
    role: str
    rule_version: str
    games: int
    wins: int
    rate: float
    low: float  # 95% interval
    high: float
    enough: bool  # False means "not clear yet": too few games to compare cards


class CoachHistory(BaseModel):
    side: Literal["wolf", "villager"]
    generations: list[Generation]


class PlayStatus(BaseModel):
    available: bool
    reason: str  # why play mode is not available, or "" when it is


class PlayStarted(BaseModel):
    id: str


class PlayState(BaseModel):
    id: str
    status: Literal["running", "finished", "stopped"]
    game_id: str | None  # the stored game, once it has finished
    reason: str | None  # why it stopped


class CoachRunRequest(BaseModel):
    generations: int = 1
    games: int = 6  # games per arm


class CoachRunStatus(BaseModel):
    id: str
    state: Literal["queued", "running", "finished", "stopped", "failed"]
    generations_done: int
    cost: float
