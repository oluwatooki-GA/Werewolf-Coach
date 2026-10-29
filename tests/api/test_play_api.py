"""Play mode over HTTP: pick four cards, a game is played in the background, read it when done."""

import asyncio
import time
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from api_support import played
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings
from werewolf.play.service import VisitorGame
from werewolf.store import make_engine
from werewolf.store.play import new_session
from werewolf.store.tables import games

REPO = Path(__file__).resolve().parents[2]
PICKS = {
    "wolf": "wolf.lie_low",
    "villager": "villager.track_votes",
    "seer": "seer.reveal_now",
    "doctor": "doctor.protect_seer",
}


def settings(model: str = "fake", **more: object) -> ApiSettings:
    return ApiSettings(
        web_origin="http://site.test", cards_dir=REPO / "cards", play_model=model, **more
    )  # type: ignore[arg-type]


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return make_engine(f"sqlite:///{tmp_path / 'play.db'}")


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    # a `with` block keeps one event loop alive, so a game started by one request can go on
    with TestClient(create_app(engine, settings())) as c:
        yield c


def wait_for(client: TestClient, play_id: str, done: set[str] | None = None) -> dict[str, object]:
    done = done or {"finished", "stopped"}
    for _ in range(200):
        state: dict[str, object] = client.get(f"/play/{play_id}").json()
        if state["status"] in done:
            return state
        time.sleep(0.05)
    raise AssertionError(f"still {state['status']} after 10 seconds")


def test_play_is_open_when_a_model_is_set_and_closed_with_a_reason_when_not(engine: Engine) -> None:
    with TestClient(create_app(engine, settings())) as open_:
        assert open_.get("/play/status").json() == {"available": True, "reason": "", "games_left": 3}
    with TestClient(create_app(engine, settings(model=""))) as closed:
        status = closed.get("/play/status").json()
        assert status["available"] is False and "not set up" in status["reason"]
        assert closed.post("/play", json=PICKS).status_code == 503


def test_starting_a_game_answers_at_once_and_it_finishes_in_the_background(
    client: TestClient,
) -> None:
    started = client.post("/play", json=PICKS)
    assert started.status_code == 202
    play_id = started.json()["id"]
    state = wait_for(client, play_id)
    assert state["status"] == "finished" and state["reason"] is None
    game = client.get(f"/games/{state['game_id']}")
    assert game.status_code == 200
    summary = client.get("/games").json()["games"][0]
    assert summary["source"] == "play" and summary["rule_version"] == "v3"


def test_a_bad_card_is_refused_with_the_reason_before_anything_starts(client: TestClient) -> None:
    refused = client.post("/play", json={**PICKS, "wolf": "villager.track_votes"})
    assert refused.status_code == 422
    assert "Villager card, not a Werewolf card" in refused.json()["detail"]
    assert client.get("/games").json()["total"] == 0


def test_a_missing_choice_is_refused(client: TestClient) -> None:
    refused = client.post("/play", json={"wolf": "default"})
    assert refused.status_code == 422


def test_nothing_but_the_four_cards_is_accepted(client: TestClient) -> None:
    for extra in ({"model": "claude-opus-5-5"}, {"seed": 1}, {"max_spend": "100"}):
        assert client.post("/play", json={**PICKS, **extra}).status_code == 422
    assert client.get("/games").json()["total"] == 0


def test_an_unknown_game_is_a_404(client: TestClient) -> None:
    assert client.get("/play/nope").status_code == 404


class Slow:
    """A game that waits until it is let go, so a test can hold some games open."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        # built now: `played` starts its own event loop, so it cannot run inside a game
        self.logs = [played(3), played(4), played(5)]
        self.used = 0

    async def __call__(self, picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
        log = self.logs[self.used]
        self.used += 1
        await self.release.wait()
        return VisitorGame("finished", log, Decimal("0"))


def test_only_two_games_run_at_once(engine: Engine) -> None:
    app = create_app(engine, settings())
    slow = Slow()
    app.state.play_run = slow
    with TestClient(app) as client:
        first = client.post("/play", json=PICKS)
        second = client.post("/play", json=PICKS)
        third = client.post("/play", json=PICKS)
        assert (first.status_code, second.status_code) == (202, 202)
        assert third.status_code == 429 and "two games" in third.json()["detail"]
        assert client.get(f"/play/{first.json()['id']}").json()["status"] == "running"
        client.portal.call(slow.release.set)  # type: ignore[union-attr]
        assert wait_for(client, first.json()["id"])["status"] == "finished"
        assert wait_for(client, second.json()["id"])["status"] == "finished"
        assert client.post("/play", json=PICKS).status_code == 202


def test_a_game_that_stopped_is_reported_but_never_listed_as_a_real_game(engine: Engine) -> None:
    broken = played(3)

    async def stops(picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
        return VisitorGame("stopped", broken, Decimal("0.3"), reason="most answers failed")

    app = create_app(engine, settings())
    app.state.play_run = stops
    with TestClient(app) as client:
        state = wait_for(client, client.post("/play", json=PICKS).json()["id"])
        assert state["status"] == "stopped" and state["reason"] == "most answers failed"
        assert state["game_id"] is None
        assert client.get("/games").json()["total"] == 0
        assert client.get("/results").json() == []
        with engine.connect() as conn:  # kept in the database, out of sight
            assert [r.status for r in conn.execute(select(games.c.status))] == ["stopped"]


def test_a_game_that_crashes_is_reported_as_stopped_not_lost(engine: Engine) -> None:
    async def crashes(picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
        raise RuntimeError("OPENAI_API_KEY is not set")

    app = create_app(engine, settings())
    app.state.play_run = crashes
    with TestClient(app) as client:
        state = wait_for(client, client.post("/play", json=PICKS).json()["id"])
        assert state["status"] == "stopped" and "could not be played" in str(state["reason"])
        assert (
            client.post("/play", json=PICKS).status_code == 202
        )  # and it no longer counts as running


def test_a_game_still_running_when_the_server_restarts_is_marked_stopped(engine: Engine) -> None:
    with engine.begin() as conn:
        play_id = new_session(conn, PICKS)
    with TestClient(create_app(engine, settings())) as client:
        state = client.get(f"/play/{play_id}").json()
        assert state["status"] == "stopped" and "restarted" in state["reason"]


def test_the_state_of_a_game_has_only_what_the_page_needs(client: TestClient) -> None:
    play_id = client.post("/play", json=PICKS).json()["id"]
    state = wait_for(client, play_id)
    assert set(state) == {"id", "status", "game_id", "reason"}


def test_a_game_that_cannot_be_saved_ends_as_stopped_not_running_forever(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> str:
        raise RuntimeError("the database is full")

    monkeypatch.setattr("werewolf.api.play.add_game", broken)
    with TestClient(create_app(engine, settings())) as client:
        state = wait_for(client, client.post("/play", json=PICKS).json()["id"])
        assert state["status"] == "stopped" and "could not be saved" in str(state["reason"])
