"""Play mode live: a game still being played can be read as the same entries a replay uses."""

import asyncio
import threading
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from api_support import play_body
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from werewolf.agents.scripted import policy
from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings
from werewolf.engine.actions import Agent, BidAction, BidTask, Task, VoteTask
from werewolf.engine.game import play_game
from werewolf.engine.log import to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings
from werewolf.engine.views import PlayerView
from werewolf.play.service import VisitorGame
from werewolf.store import make_engine

REPO = Path(__file__).resolve().parents[2]
BODY = play_body()


class Talker:
    """One scripted player that says one thing on its first bid, with a private thought, and waits
    at the first vote until the test lets the game go on."""

    def __init__(self, name: str, inner: Agent, game: "Halfway") -> None:
        self.name, self.inner, self.game, self.bid = name, inner, game, False

    async def act(self, view: PlayerView, task: Task) -> object:
        if isinstance(task, VoteTask):
            self.game.arrived.set()
            await self.game.release.wait()
        if isinstance(task, BidTask) and not task.free and not self.bid:
            self.bid = True
            return BidAction(bid=1, message=f"{self.name} speaking.", note=f"{self.name} thinks")
        return await self.inner.act(view, task)


class Halfway:
    """Plays a real game on the v3 rules, held at the first vote until `release` is set."""

    def __init__(self, then: Callable[[GameState], VisitorGame] | None = None) -> None:
        self.release = asyncio.Event()
        self.arrived = threading.Event()
        self.state: GameState | None = None
        self.then = then

    async def __call__(
        self,
        seed: int,
        picks: Mapping[str, str],
        config: ApiSettings,
        on_start: Callable[[GameState], None],
    ) -> VisitorGame:
        players = new_game(seed).players
        wolves = [p.name for p in players if p.role is Role.WEREWOLF]
        agents: dict[str, Agent] = {p.name: Talker(p.name, policy(wolves), self) for p in players}
        self.state = await play_game(
            seed, Settings(wolf_chat_messages=5), agents, on_start=on_start
        )
        if self.then is not None:
            return self.then(self.state)
        return VisitorGame("finished", to_log(self.state, run_id="live-test"), Decimal("0"))


def settings() -> ApiSettings:
    return ApiSettings(web_origin="http://site.test", cards_dir=REPO / "cards", play_model="fake")


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return make_engine(f"sqlite:///{tmp_path / 'live.db'}")


def app_with(engine: Engine, run: object):  # type: ignore[no-untyped-def]
    app = create_app(engine, settings())
    app.state.play_run = run
    return app


def wait_for(client: TestClient, play_id: str) -> dict[str, object]:
    for _ in range(200):
        state: dict[str, object] = client.get(f"/play/{play_id}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("still running after 10 seconds")


def test_half_way_through_a_game_its_entries_so_far_can_be_read(engine: Engine) -> None:
    halfway = Halfway()
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        live = client.get(f"/play/{play_id}/live").json()
        assert live["status"] == "running" and live["game_id"] is None and live["reason"] is None
        assert live["total"] == len(live["entries"]) > 0
        kinds = [e["kind"] for e in live["entries"]]
        assert (
            "night" in kinds and "line" in kinds and "vote" not in kinds
        )  # held at the first vote
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        wait_for(client, play_id)


def test_a_line_comes_with_the_thought_that_wrote_it_as_soon_as_it_is_there(
    engine: Engine,
) -> None:
    halfway = Halfway()
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        entries = client.get(f"/play/{play_id}/live").json()["entries"]
        lines = [e for e in entries if e["kind"] == "line"]
        assert lines and all(e["subtext"]["note"] == f"{e['speaker']} thinks" for e in lines)
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        wait_for(client, play_id)


def test_after_returns_only_what_is_new_and_the_rest_matches_the_finished_replay(
    engine: Engine,
) -> None:
    halfway = Halfway()
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        everything = client.get(f"/play/{play_id}/live").json()
        total = everything["total"]
        assert total >= 3
        later = client.get(f"/play/{play_id}/live", params={"after": 2}).json()
        assert later["total"] == total and later["entries"] == everything["entries"][2:]
        nothing = client.get(f"/play/{play_id}/live", params={"after": total}).json()
        assert nothing["entries"] == [] and nothing["total"] == total
        beyond = client.get(f"/play/{play_id}/live", params={"after": total + 50}).json()
        assert beyond["entries"] == []
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        state = wait_for(client, play_id)
        replay = client.get(f"/games/{state['game_id']}/replay").json()
        assert replay["entries"][:total] == everything["entries"]  # nothing skipped or changed


def test_a_finished_game_says_so_and_gives_the_game_to_open(engine: Engine) -> None:
    halfway = Halfway()
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        state = wait_for(client, play_id)
        live = client.get(f"/play/{play_id}/live").json()
        assert live["status"] == "finished" and live["game_id"] == state["game_id"]
        assert live["entries"] == [] and live["reason"] is None


def test_a_stopped_game_gives_its_reason(engine: Engine) -> None:
    def stops(state: GameState) -> VisitorGame:
        return VisitorGame("stopped", None, Decimal("0.2"), reason="the run budget is used up")

    halfway = Halfway(then=stops)
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        wait_for(client, play_id)
        live = client.get(f"/play/{play_id}/live").json()
        assert live["status"] == "stopped" and live["reason"] == "the run budget is used up"
        assert live["entries"] == [] and live["game_id"] is None


def test_a_game_that_has_not_begun_to_play_is_running_with_nothing_yet(engine: Engine) -> None:
    class Waiting:
        async def __call__(self, *args: object) -> VisitorGame:
            await asyncio.Event().wait()  # never starts, so nothing is registered
            raise AssertionError("unreachable")

    with TestClient(app_with(engine, Waiting())) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        live = client.get(f"/play/{play_id}/live").json()
        assert (live["status"], live["total"], live["entries"]) == ("running", 0, [])


def test_an_unknown_game_is_404_and_a_bad_cursor_is_422(engine: Engine) -> None:
    with TestClient(create_app(engine, settings())) as client:
        assert client.get("/play/nope/live").status_code == 404
        play_id = client.post("/play", json=BODY).json()["id"]
        wait_for(client, play_id)
        for after in ("-1", "x", "1.5"):
            assert client.get(f"/play/{play_id}/live", params={"after": after}).status_code == 422


def test_the_live_state_is_let_go_however_the_game_ends(engine: Engine) -> None:
    def stops(state: GameState) -> VisitorGame:
        return VisitorGame("stopped", None, Decimal("0"), reason="stopped")

    class Crashes(Halfway):
        async def __call__(  # type: ignore[override]
            self,
            seed: int,
            picks: Mapping[str, str],
            config: ApiSettings,
            on_start: Callable[[GameState], None],
        ) -> VisitorGame:
            on_start(new_game(seed))  # registered, then the game blows up
            raise RuntimeError("the model client broke")

    for run in (Halfway(), Halfway(then=stops), Crashes()):
        app = app_with(engine, run)
        with TestClient(app) as client:
            play_id = client.post("/play", json=BODY).json()["id"]
            if isinstance(run, Crashes):
                wait_for(client, play_id)
            else:
                assert run.arrived.wait(10)
                assert play_id in app.state.play_live  # while it is being played
                client.portal.call(run.release.set)  # type: ignore[union-attr]
                wait_for(client, play_id)
            assert app.state.play_live == {}


def test_the_live_answer_is_only_what_the_page_needs(engine: Engine) -> None:
    halfway = Halfway()
    with TestClient(app_with(engine, halfway)) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        assert halfway.arrived.wait(10)
        live = client.get(f"/play/{play_id}/live").json()
        assert set(live) == {"status", "game_id", "reason", "total", "entries"}
        client.portal.call(halfway.release.set)  # type: ignore[union-attr]
        wait_for(client, play_id)
