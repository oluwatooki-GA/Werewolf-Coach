"""What the API sends back. These models are the contract the website is written against: they
show up in `/docs` and in `/openapi.json`, and FastAPI checks every answer against them."""

from typing import Literal

from pydantic import BaseModel

from werewolf.api.replay import Entry
from werewolf.coach.history import Generation
from werewolf.engine.log import GameLog
from werewolf.tagger.tags import DerivedTag, TagFile


class Health(BaseModel):
    """`down` (503) only when the database cannot be reached; `degraded` when play is set up with
    a model whose key is missing; a used-up cap shows as `play: paused` and is not a fault."""

    status: Literal["ok", "degraded", "down"]
    database: Literal["ok", "down"]
    provider: Literal["ok", "missing_key", "off"] = "off"  # the play model's key; never its value
    play: Literal["open", "paused", "off"] = "off"
    active_games: int = 0  # games being played right now
    faults: list[str] = []  # test-only fault switches that are on: always empty in production


class GameCounts(BaseModel):
    total: int
    by_status: dict[str, int]
    by_source: dict[str, int]  # "play" are games visitors started here
    unclean: int  # games where a model call failed and fell back to a default


class PlayCounts(BaseModel):
    started: int
    finished: int
    stopped: int
    running: int


class SpendCounts(BaseModel):
    today: float  # dollars, in the day play counts in (UTC)
    total: float
    by_day: dict[str, float]


class Metrics(BaseModel):
    games: GameCounts
    play: PlayCounts
    spend: SpendCounts


class AdminPlay(BaseModel):
    id: str
    status: str
    reason: str
    cost: float
    created_at: float  # seconds since 1970
    game_id: str | None


class AdminOverview(BaseModel):
    metrics: Metrics
    recent: list[AdminPlay]  # the latest games visitors started, newest first
    active_games: int
    play_model: str


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
    games_left: int | None = (
        None  # games the caps can still pay for today; None if play is not set up
    )


class PlaySeat(BaseModel):
    name: str
    role: str


class PlayTable(BaseModel):
    seed: int  # send it back with the cards: the same seed deals the same table
    default_card: str  # what a player is told when no card is chosen
    seats: list[PlaySeat]


class PlayStarted(BaseModel):
    id: str


class PlayState(BaseModel):
    id: str
    status: Literal["running", "finished", "stopped"]
    game_id: str | None  # the stored game, once it has finished
    reason: str | None  # why it stopped


class PlayLive(BaseModel):
    """A game being played, as far as it has got. `entries` are those from the asked-for index on;
    `total` is how many there are now, so the next ask is `after=total`."""

    status: Literal["running", "finished", "stopped"]
    game_id: str | None  # the stored game to open, once it has finished
    reason: str | None  # why it stopped
    total: int
    entries: list[Entry]


class CoachRunRequest(BaseModel):
    generations: int = 1
    games: int = 6  # games per arm


class CoachRunStatus(BaseModel):
    id: str
    state: Literal["queued", "running", "finished", "stopped", "failed"]
    generations_done: int
    cost: float
