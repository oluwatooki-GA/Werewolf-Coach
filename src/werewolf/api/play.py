"""Play mode: a visitor picks a strategy card for each player and the agents play a game with them.

`GET /play/table` deals a table (a seed, and the eight seats with their roles). `POST /play` takes
that seed and a card for every seat and answers at once with an id; the game is played in the
background, in this process. `GET /play/{id}` says `running`, `finished` (with the stored game's id,
which opens as a replay) or `stopped` (with why). A game still running when the server restarts is
marked stopped. The seed and the cards are the only input: no model or budget comes from
the visitor.

Money: a game starts only if today's cap and the total cap can both pay for one more (see
`play/budget.py`), each game has its own spending limit, and one address may try to start at most
`play_requests_per_minute` games a minute. Replays and the board are never touched by any of this.
"""

import asyncio
import logging
import secrets
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from werewolf import runtime
from werewolf.agents.prompt import DEFAULT_CARD
from werewolf.api.deps import DB, ApiSettings, Settings
from werewolf.api.replay import replay_entries
from werewolf.api.schemas import (
    PlayLive,
    PlaySeat,
    PlayStarted,
    PlayState,
    PlayStatus,
    PlayTable,
)
from werewolf.engine.state import GameState
from werewolf.play.budget import Caps, Verdict, check
from werewolf.play.service import (
    SEEDS,
    PickError,
    VisitorGame,
    check_picks,
    play_visitor_game,
    seats,
)
from werewolf.store.games import add_game
from werewolf.store.play import add_spend, finish_session, get_session, new_session

router = APIRouter(prefix="/play", tags=["play"])
log = logging.getLogger(__name__)
RunGame = Callable[
    [int, Mapping[str, str], ApiSettings, Callable[[GameState], None]], Awaitable[VisitorGame]
]
NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


class PlayRequest(BaseModel):
    """A table's seed and a card for each seat, and nothing else: an extra field is refused."""

    model_config = ConfigDict(extra="forbid")

    seed: int = Field(ge=0, lt=SEEDS)
    cards: dict[str, str]  # seat name -> "id@version", or "default"


async def run_visitor(
    seed: int,
    picks: Mapping[str, str],
    config: ApiSettings,
    on_start: Callable[[GameState], None],
) -> VisitorGame:
    """Play one game for real: the free scripted players, or the configured model with the
    per-game spending limit."""
    client = None
    max_tokens = 300
    if config.play_model != "fake":
        client = runtime.build_client(config.play_model, config.play_game_budget)
        max_tokens = runtime.default_max_tokens(config.play_model, 300)
    return await play_visitor_game(
        seed,
        picks,
        model=config.play_model,
        client=client,
        max_tokens=max_tokens,
        directory=config.cards_dir,
        on_start=on_start,
    )


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def _verdict(request: Request, db: DB, config: ApiSettings) -> Verdict:
    caps = Caps(config.play_daily_cap, config.play_total_cap, config.play_game_estimate)
    running = len(request.app.state.play_tasks)
    with db.connect() as conn:
        return check(conn, caps, running=running, day=request.app.state.play_day())


def _limit_rate(request: Request, config: ApiSettings) -> None:
    """At most `play_requests_per_minute` attempts a minute from one address, counted whether the
    attempt was good or not."""
    who = request.client.host if request.client else "unknown"
    now: float = request.app.state.play_clock()
    hits: dict[str, deque[float]] = request.app.state.play_hits
    window = hits.setdefault(who, deque())
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= config.play_requests_per_minute:
        raise HTTPException(429, "Too many requests. Wait a minute and try again.")
    window.append(now)


async def _play(request: Request, play_id: str, seed: int, picks: Mapping[str, str]) -> None:
    engine, config = request.app.state.engine, request.app.state.settings
    run: RunGame = request.app.state.play_run

    def finish(game: VisitorGame | None, reason: str) -> None:
        with engine.begin() as conn:
            stored = None
            if game is not None and game.log is not None:
                stored = add_game(conn, game.log, source="play", status=game.status)
            status = game.status if game is not None else "stopped"
            if game is not None and game.cost:
                add_spend(conn, request.app.state.play_day(), float(game.cost))
            finish_session(
                conn,
                play_id,
                status,
                game_id=stored if status == "finished" else None,
                reason=reason,
                cost=float(game.cost) if game is not None else 0.0,
            )

    live: dict[str, GameState] = request.app.state.play_live
    try:
        try:
            game = await run(seed, picks, config, lambda state: live.__setitem__(play_id, state))
        except Exception:  # a game must end as stopped, never as a row that says running forever
            log.exception("play game %s crashed", play_id)
            await asyncio.to_thread(finish, None, "the game could not be played; try again later")
            return
        try:
            await asyncio.to_thread(finish, game, game.reason or "")
        except Exception:  # played but not stored: say so rather than leave it running
            log.exception("play game %s could not be saved", play_id)
            await asyncio.to_thread(finish, None, "the game was played but could not be saved")
    finally:
        live.pop(play_id, None)  # after the row says it is over, so a reader never sees a gap


@router.get("/status")
def status(request: Request, db: DB, config: Settings) -> PlayStatus:
    if not config.play_model:
        return PlayStatus(available=False, reason="play mode is not set up on this server")
    verdict = _verdict(request, db, config)
    if verdict.state == "paused":
        return PlayStatus(available=False, reason=verdict.reason, games_left=0)
    return PlayStatus(available=True, reason="", games_left=verdict.games_left)


@router.get("/table")
def table(seed: Annotated[int | None, Query(ge=0, lt=SEEDS)] = None) -> PlayTable:
    """The seats and roles a seed deals; with no seed, a new table."""
    seed = secrets.randbelow(SEEDS) if seed is None else seed
    return PlayTable(
        seed=seed,
        default_card=DEFAULT_CARD,
        seats=[PlaySeat(name=n, role=r.value) for n, r in seats(seed)],
    )


@router.post("", status_code=202)
async def start(request: Request, body: PlayRequest, db: DB, config: Settings) -> PlayStarted:
    _limit_rate(request, config)
    if not config.play_model:
        raise HTTPException(503, "play mode is not set up on this server")
    verdict = _verdict(request, db, config)
    if verdict.state == "paused":
        raise HTTPException(503, f"Play mode is paused. {verdict.reason}")
    try:
        check_picks(body.seed, body.cards, config.cards_dir)
    except PickError as exc:
        raise HTTPException(422, str(exc)) from exc
    running: set[asyncio.Task[None]] = request.app.state.play_tasks
    if len(running) >= config.play_max_games:
        many = NUMBERS.get(config.play_max_games, str(config.play_max_games))
        raise HTTPException(429, f"Only {many} games can be played at once. Try again in a minute.")
    if verdict.state == "busy":
        raise HTTPException(429, verdict.reason)
    with db.begin() as conn:
        play_id = new_session(conn, body.cards)
    task = asyncio.create_task(_play(request, play_id, body.seed, body.cards))
    running.add(task)
    task.add_done_callback(running.discard)
    return PlayStarted(id=play_id)


@router.get("/{play_id}")
def state(play_id: str, db: DB) -> PlayState:
    with db.connect() as conn:
        row = get_session(conn, play_id)
    if row is None:
        raise HTTPException(404, "no such game")
    return PlayState(id=row.id, status=row.status, game_id=row.game_id, reason=row.reason or None)


@router.get("/{play_id}/live")
def live(
    request: Request, play_id: str, db: DB, after: Annotated[int, Query(ge=0)] = 0
) -> PlayLive:
    """A game being played, as the entries a replay is made of, from index `after` on. Once it is
    over it says how it ended and gives no entries: the stored game is read from the replay."""
    state: GameState | None = request.app.state.play_live.get(play_id)
    if state is not None:
        # events first, then calls: a call is recorded before the event it led to, so every event
        # taken here has its call in the (later) list of calls
        events = list(state.events)
        calls = list(state.calls)
        roles = {p.name: p.role for p in state.players}
        entries = replay_entries(roles, events, calls)
        return PlayLive(
            status="running", game_id=None, reason=None, total=len(entries), entries=entries[after:]
        )
    with db.connect() as conn:
        row = get_session(conn, play_id)
    if row is None:
        raise HTTPException(404, "no such game")
    return PlayLive(
        status=row.status, game_id=row.game_id, reason=row.reason or None, total=0, entries=[]
    )
