"""Play mode: a visitor picks one strategy card for each role and the agents play a game with them.

`POST /play` takes the four picks and answers at once with an id; the game is played in the
background, in this process. `GET /play/{id}` says `running`, `finished` (with the stored game's id,
which opens as a replay) or `stopped` (with why). A game still running when the server restarts is
marked stopped. The picks are the only input: no model, seed or budget comes from the visitor.

Caps on spending are T8; the number of games at once is limited here.
"""

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable, Mapping

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from werewolf import runtime
from werewolf.api.deps import DB, ApiSettings, Settings
from werewolf.api.schemas import PlayStarted, PlayState, PlayStatus
from werewolf.play.service import PickError, VisitorGame, check_picks, play_visitor_game
from werewolf.store.games import add_game
from werewolf.store.play import finish_session, get_session, new_session

router = APIRouter(prefix="/play", tags=["play"])
log = logging.getLogger(__name__)
RunGame = Callable[[Mapping[str, str], ApiSettings], Awaitable[VisitorGame]]
NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


class PlayRequest(BaseModel):
    """The four cards, and nothing else: an extra field is refused."""

    model_config = ConfigDict(extra="forbid")

    wolf: str
    villager: str
    seer: str
    doctor: str


async def run_visitor(picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
    """Play one game for real: the free scripted players, or the configured model with the
    per-game spending limit."""
    client = None
    max_tokens = 300
    if config.play_model != "fake":
        client = runtime.build_client(config.play_model, config.play_game_budget)
        max_tokens = runtime.default_max_tokens(config.play_model, 300)
    return await play_visitor_game(
        picks,
        secrets.randbelow(1_000_000),
        model=config.play_model,
        client=client,
        max_tokens=max_tokens,
        directory=config.cards_dir,
    )


async def _play(request: Request, play_id: str, picks: Mapping[str, str]) -> None:
    engine, config = request.app.state.engine, request.app.state.settings
    run: RunGame = request.app.state.play_run

    def finish(game: VisitorGame | None, reason: str) -> None:
        with engine.begin() as conn:
            stored = None
            if game is not None and game.log is not None:
                stored = add_game(conn, game.log, source="play", status=game.status)
            status = game.status if game is not None else "stopped"
            finish_session(
                conn,
                play_id,
                status,
                game_id=stored if status == "finished" else None,
                reason=reason,
                cost=float(game.cost) if game is not None else 0.0,
            )

    try:
        game = await run(picks, config)
    except Exception:  # a game must end as stopped, never as a row that says running forever
        log.exception("play game %s crashed", play_id)
        await asyncio.to_thread(finish, None, "the game could not be played; try again later")
        return
    try:
        await asyncio.to_thread(finish, game, game.reason or "")
    except Exception:  # played but not stored: say so rather than leave it running
        log.exception("play game %s could not be saved", play_id)
        await asyncio.to_thread(finish, None, "the game was played but could not be saved")


@router.get("/status")
def status(config: Settings) -> PlayStatus:
    if not config.play_model:
        return PlayStatus(available=False, reason="play mode is not set up on this server")
    return PlayStatus(available=True, reason="")


@router.post("", status_code=202)
async def start(request: Request, picks: PlayRequest, db: DB, config: Settings) -> PlayStarted:
    if not config.play_model:
        raise HTTPException(503, "play mode is not set up on this server")
    try:
        check_picks(picks.model_dump(), config.cards_dir)
    except PickError as exc:
        raise HTTPException(422, str(exc)) from exc
    running: set[asyncio.Task[None]] = request.app.state.play_tasks
    if len(running) >= config.play_max_games:
        many = NUMBERS.get(config.play_max_games, str(config.play_max_games))
        raise HTTPException(429, f"Only {many} games can be played at once. Try again in a minute.")
    with db.begin() as conn:
        play_id = new_session(conn, picks.model_dump())
    task = asyncio.create_task(_play(request, play_id, picks.model_dump()))
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
