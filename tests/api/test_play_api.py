"""Play mode over HTTP: pick a card for each player, the game is played in the background."""

import asyncio
import time
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from api_support import play_body, played, seat_of
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from werewolf.agents.prompt import DEFAULT_CARD
from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings
from werewolf.api.play import UNAVAILABLE, public_reason
from werewolf.engine.roles import Role
from werewolf.play.service import VisitorGame, seats
from werewolf.store import make_engine
from werewolf.store.play import new_session
from werewolf.store.tables import games

REPO = Path(__file__).resolve().parents[2]
BODY = play_body()
SPENDING_TEXT = "This game reached its spending limit, so it was stopped."
FAILED_TEXT = "Most of the AI's answers failed, so the game was stopped."


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
        assert open_.get("/play/status").json() == {
            "available": True,
            "reason": "",
            "games_left": 3,
        }
    with TestClient(create_app(engine, settings(model=""))) as closed:
        status = closed.get("/play/status").json()
        assert status["available"] is False and "not set up" in status["reason"]
        assert closed.post("/play", json=BODY).status_code == 503


def test_starting_a_game_answers_at_once_and_it_finishes_in_the_background(
    client: TestClient,
) -> None:
    started = client.post("/play", json=BODY)
    assert started.status_code == 202
    play_id = started.json()["id"]
    state = wait_for(client, play_id)
    assert state["status"] == "finished" and state["reason"] is None
    game = client.get(f"/games/{state['game_id']}")
    assert game.status_code == 200
    summary = client.get("/games").json()["games"][0]
    assert summary["source"] == "play" and summary["rule_version"] == "v3"


def test_a_bad_card_is_refused_with_the_reason_before_anything_starts(client: TestClient) -> None:
    villager = seat_of(Role.VILLAGER)
    refused = client.post("/play", json=play_body(**{villager: "wolf.lie_low"}))
    assert refused.status_code == 422
    assert f"Werewolf card but {villager} is the Villager" in refused.json()["detail"]
    assert client.get("/games").json()["total"] == 0


def test_a_player_left_out_is_refused(client: TestClient) -> None:
    gone = seat_of(Role.SEER)
    body = play_body()
    del body["cards"][gone]  # type: ignore[attr-defined]
    refused = client.post("/play", json=body)
    assert refused.status_code == 422 and gone in refused.json()["detail"]


def test_a_missing_part_is_refused(client: TestClient) -> None:
    assert client.post("/play", json={"seed": 3}).status_code == 422
    assert client.post("/play", json={"cards": {}}).status_code == 422


def test_nothing_but_the_seed_and_the_cards_is_accepted(client: TestClient) -> None:
    for extra in ({"model": "claude-opus-5-5"}, {"max_spend": "100"}, {"rounds": 9}):
        assert client.post("/play", json={**BODY, **extra}).status_code == 422
    assert client.get("/games").json()["total"] == 0


def test_the_seed_must_be_a_small_whole_number(client: TestClient) -> None:
    for seed in (-1, 1_000_000, "three", 1.5):
        assert client.post("/play", json={**BODY, "seed": seed}).status_code == 422


def test_each_player_plays_the_card_chosen_for_that_player(client: TestClient) -> None:
    first, second = seat_of(Role.WEREWOLF, 0), seat_of(Role.WEREWOLF, 1)
    body = play_body(**{first: "wolf.lie_low", second: "wolf.fake_seer"})
    play_id = client.post("/play", json=body).json()["id"]
    state = wait_for(client, play_id)
    assert state["status"] == "finished"
    players = {
        p["name"]: p for p in client.get(f"/games/{state['game_id']}/replay").json()["players"]
    }
    assert players[first]["card"].startswith("wolf.lie_low@")
    assert players[second]["card"].startswith("wolf.fake_seer@")


def test_the_table_shows_the_seats_and_roles_a_seed_deals(client: TestClient) -> None:
    table = client.get("/play/table", params={"seed": 3}).json()
    assert table["seed"] == 3
    assert [(s["name"], s["role"]) for s in table["seats"]] == [
        (name, role.value) for name, role in seats(3)
    ]


def test_the_table_carries_what_the_default_card_says(client: TestClient) -> None:
    table = client.get("/play/table", params={"seed": 3}).json()
    assert table["default_card"] == DEFAULT_CARD and "Play to win" in table["default_card"]


def test_a_table_without_a_seed_is_dealt_a_new_seed_that_can_be_played(client: TestClient) -> None:
    table = client.get("/play/table").json()
    assert 0 <= table["seed"] < 1_000_000 and len(table["seats"]) == 8
    assert [(s["name"], s["role"]) for s in table["seats"]] == [
        (name, role.value) for name, role in seats(table["seed"])
    ]


def test_a_bad_seed_for_a_table_is_refused(client: TestClient) -> None:
    for seed in ("-1", "1000000", "x"):
        assert client.get("/play/table", params={"seed": seed}).status_code == 422


def test_an_unknown_game_is_a_404(client: TestClient) -> None:
    assert client.get("/play/nope").status_code == 404


class Slow:
    """A game that waits until it is let go, so a test can hold some games open."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        # built now: `played` starts its own event loop, so it cannot run inside a game
        self.logs = [played(3), played(4), played(5)]
        self.used = 0

    async def __call__(
        self, seed: int, picks: Mapping[str, str], config: ApiSettings, *_: object
    ) -> VisitorGame:
        log = self.logs[self.used]
        self.used += 1
        await self.release.wait()
        return VisitorGame("finished", log, Decimal("0"))


def test_only_two_games_run_at_once(engine: Engine) -> None:
    app = create_app(engine, settings())
    slow = Slow()
    app.state.play_run = slow
    with TestClient(app) as client:
        first = client.post("/play", json=BODY)
        second = client.post("/play", json=BODY)
        third = client.post("/play", json=BODY)
        assert (first.status_code, second.status_code) == (202, 202)
        assert third.status_code == 429 and "two games" in third.json()["detail"]
        assert client.get(f"/play/{first.json()['id']}").json()["status"] == "running"
        client.portal.call(slow.release.set)  # type: ignore[union-attr]
        assert wait_for(client, first.json()["id"])["status"] == "finished"
        assert wait_for(client, second.json()["id"])["status"] == "finished"
        assert client.post("/play", json=BODY).status_code == 202


def test_a_game_that_stopped_is_reported_but_never_listed_as_a_real_game(engine: Engine) -> None:
    broken = played(3)

    async def stops(
        seed: int, picks: Mapping[str, str], config: ApiSettings, *_: object
    ) -> VisitorGame:
        return VisitorGame(
            "stopped",
            broken,
            Decimal("0.3"),
            reason="9 of 12 answers failed, so this was not a real game",
        )

    app = create_app(engine, settings())
    app.state.play_run = stops
    with TestClient(app) as client:
        state = wait_for(client, client.post("/play", json=BODY).json()["id"])
        assert state["status"] == "stopped" and state["reason"] == FAILED_TEXT
        assert state["game_id"] is None
        assert client.get("/games").json()["total"] == 0
        assert client.get("/results").json() == []
        with engine.connect() as conn:  # kept in the database, out of sight
            assert [r.status for r in conn.execute(select(games.c.status))] == ["stopped"]


def test_a_game_that_crashes_is_reported_as_stopped_not_lost(engine: Engine) -> None:
    async def crashes(
        seed: int, picks: Mapping[str, str], config: ApiSettings, *_: object
    ) -> VisitorGame:
        raise RuntimeError("OPENAI_API_KEY is not set")

    app = create_app(engine, settings())
    app.state.play_run = crashes
    with TestClient(app) as client:
        state = wait_for(client, client.post("/play", json=BODY).json()["id"])
        assert state["status"] == "stopped" and "could not be played" in str(state["reason"])
        assert (
            client.post("/play", json=BODY).status_code == 202
        )  # and it no longer counts as running


def test_a_game_still_running_when_the_server_restarts_is_marked_stopped(engine: Engine) -> None:
    with engine.begin() as conn:
        play_id = new_session(conn, BODY["cards"])  # type: ignore[arg-type]
    with TestClient(create_app(engine, settings())) as client:
        state = client.get(f"/play/{play_id}").json()
        assert state["status"] == "stopped" and "restarted" in state["reason"]


def test_the_state_of_a_game_has_only_what_the_page_needs(client: TestClient) -> None:
    play_id = client.post("/play", json=BODY).json()["id"]
    state = wait_for(client, play_id)
    assert set(state) == {"id", "status", "game_id", "reason"}


def test_a_game_that_cannot_be_saved_ends_as_stopped_not_running_forever(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> str:
        raise RuntimeError("the database is full")

    monkeypatch.setattr("werewolf.api.play.add_game", broken)
    with TestClient(create_app(engine, settings())) as client:
        state = wait_for(client, client.post("/play", json=BODY).json()["id"])
        assert state["status"] == "stopped" and "could not be saved" in str(state["reason"])


# --- what a visitor is told when a game stops --------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "told"),
    [
        (
            "run budget $0.15 would be passed",
            "This game reached its spending limit, so it was stopped.",
        ),
        (
            "openai refused the call (check the API key): litellm.AuthenticationError: invalid",
            UNAVAILABLE,
        ),
        (
            "openai has no model gpt-4.1-nano: litellm.NotFoundError: deprecated",
            UNAVAILABLE,
        ),
        (
            "openai rate limit reached: 429 from the provider",
            UNAVAILABLE,
        ),
        (
            "cannot write to /app/data: permission denied",
            UNAVAILABLE,
        ),
        (
            "166 of 166 answers failed, so this was not a real game "
            "(is the model provider out of credit?)",
            FAILED_TEXT,
        ),
        (
            "the server restarted while this game was running",
            "The server restarted while this game was running.",
        ),
        (
            "the game could not be played; try again later",
            "The game could not be played. Please try again later.",
        ),
        (
            "the game was played but could not be saved",
            "The game was played but could not be saved. Please try again later.",
        ),
    ],
)
def test_a_visitor_is_told_a_plain_reason_never_the_providers_own_words(
    raw: str, told: str
) -> None:
    assert public_reason(raw) == told
    for leak in ("litellm", "API key", "credit", "/app", "gpt-", "openai", "429"):
        assert leak.lower() not in public_reason(raw).lower()


def test_the_page_and_the_live_route_both_give_the_plain_reason_but_the_owner_keeps_the_raw_one(
    engine: Engine,
) -> None:
    raw = "openai refused the call (check the API key): litellm.AuthenticationError: invalidated"

    async def refused(*args: object) -> VisitorGame:
        return VisitorGame("stopped", None, Decimal("0"), reason=raw)

    app = create_app(engine, ApiSettings(
        web_origin="http://site.test", cards_dir=REPO / "cards", play_model="fake",
        admin_token="t0ken",
    ))  # fmt: skip
    app.state.play_run = refused
    with TestClient(app) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        wait_for(client, play_id)
        told = client.get(f"/play/{play_id}").json()["reason"]
        assert "litellm" not in told and "API key" not in told
        assert client.get(f"/play/{play_id}/live").json()["reason"] == told
        recent = client.get("/admin/overview", headers={"Authorization": "Bearer t0ken"}).json()
        assert recent["recent"][0]["reason"] == raw  # the owner sees what really happened
