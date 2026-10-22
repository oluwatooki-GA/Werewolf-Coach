"""Play mode: take one seat against the AI players. SKELETON, not built yet.

The routes exist so the site and `/docs` can already point at them; every one answers "not built".
It is built after the read-only app runs properly (tasks/todo.md T6 to T10). The plan:

- `play/human.py` (T6): `HumanAgent`, an `Agent` like any other. Its `act(view, task)` puts the
  question on an outbox and waits for the browser's answer, with a turn timer; on timeout it
  returns the safe default (bid 0, abstain). The engine does not change.
- `POST /play` (T7): picks a seed and a random seat for the human, builds seven `LLMAgent`s on
  `gpt-4.1-mini`, starts `play_game(...)` as an asyncio task and returns the game id. It is open
  to everyone; GitHub login is pinned for later.
- `WS /play/{game_id}` (T7): sends each question (a `PlayerView` rendered as events, plus the
  task) and receives the answer. A closed socket ends the game as abandoned.
- Caps (T8): a `play_spend` table with today's and the total spend; a game starts only if both
  caps ($1 a day, $10 in all, settings) can pay for one, and each game has its own `run_budget`.
  When a cap is hit `GET /play/status` says so and `POST /play` answers 503; replays keep working.
- The finished game is saved with `status` and `human_seat`, like any other game. Database writes
  from the game loop run in a thread (`asyncio.to_thread`) because the engine is synchronous.
- LangGraph plays no part here: the game is a plain async loop.
"""

from fastapi import APIRouter, HTTPException, WebSocket

from werewolf.api.schemas import PlayStarted, PlayStatus

router = APIRouter(prefix="/play", tags=["play"])
NOT_BUILT = "play mode is not built yet"


@router.get("/status")
def status() -> PlayStatus:
    return PlayStatus(available=False, reason=NOT_BUILT)


@router.post("", response_model=PlayStarted)
def start() -> PlayStarted:
    raise HTTPException(501, NOT_BUILT)


@router.websocket("/{game_id}")
async def play(websocket: WebSocket, game_id: str) -> None:
    await websocket.close(code=1011, reason=NOT_BUILT)
