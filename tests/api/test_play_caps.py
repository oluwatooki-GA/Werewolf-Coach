"""Play mode and money: caps pause it, a rate limit slows abusers, replays are never affected."""

import asyncio
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from api_support import play_body, played, seat_of
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings
from werewolf.engine.roles import Role
from werewolf.play.service import VisitorGame
from werewolf.store import make_engine
from werewolf.store.play import add_spend, spent_today, spent_total

REPO = Path(__file__).resolve().parents[2]
BODY = play_body()
BAD = play_body(**{seat_of(Role.WEREWOLF): "nonsense"})
TODAY = "2026-10-29"


def settings(**more: object) -> ApiSettings:
    return ApiSettings(
        web_origin="http://site.test",
        cards_dir=REPO / "cards",
        play_model="fake",
        **more,  # type: ignore[arg-type]
    )


def app_for(engine: Engine, **more: object):  # type: ignore[no-untyped-def]
    app = create_app(engine, settings(**more))
    app.state.play_day = lambda: TODAY  # a fixed day, so a test never meets midnight
    return app


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return make_engine(f"sqlite:///{tmp_path / 'caps.db'}")


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    with TestClient(app_for(engine)) as c:
        yield c


def spend(engine: Engine, amount: float, day: str = TODAY) -> None:
    with engine.begin() as conn:
        add_spend(conn, day, amount)


def test_with_the_daily_cap_used_up_play_is_paused_but_replays_still_work(engine: Engine) -> None:
    spend(engine, 0.85)
    with TestClient(app_for(engine)) as client:
        status = client.get("/play/status").json()
        assert status["available"] is False and "tomorrow" in status["reason"].lower()
        refused = client.post("/play", json=BODY)
        assert refused.status_code == 503 and "paused" in refused.json()["detail"]
        assert client.get("/games").status_code == 200
        assert client.get("/strategies").status_code == 200


def test_with_the_total_cap_used_up_play_is_closed_with_that_reason(engine: Engine) -> None:
    for day in ("2026-10-20", "2026-10-21", "2026-10-22"):
        spend(engine, 3.30, day)
    with TestClient(app_for(engine)) as client:
        status = client.get("/play/status").json()
        assert status["available"] is False and "total" in status["reason"].lower()
        assert client.post("/play", json=BODY).status_code == 503


def test_the_caps_are_settings(engine: Engine) -> None:
    spend(engine, 0.85)
    generous = app_for(engine, play_daily_cap=Decimal("5.00"))
    with TestClient(generous) as client:
        assert client.get("/play/status").json()["available"] is True


def test_what_a_game_cost_is_added_to_today_and_to_the_total(engine: Engine) -> None:
    async def costs(seed: int, picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
        return VisitorGame("finished", log, Decimal("0.25"))

    log = played(3)
    app = app_for(engine)
    app.state.play_run = costs
    with TestClient(app) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        for _ in range(100):
            if client.get(f"/play/{play_id}").json()["status"] != "running":
                break
            asyncio.run(asyncio.sleep(0.05))
    with engine.connect() as conn:
        assert round(spent_today(conn, TODAY), 2) == 0.25
        assert round(spent_total(conn), 2) == 0.25


def test_a_stopped_game_still_counts_what_it_spent(engine: Engine) -> None:
    async def stops(seed: int, picks: Mapping[str, str], config: ApiSettings) -> VisitorGame:
        return VisitorGame("stopped", None, Decimal("0.40"), reason="the run budget is used up")

    app = app_for(engine)
    app.state.play_run = stops
    with TestClient(app) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        for _ in range(100):
            if client.get(f"/play/{play_id}").json()["status"] != "running":
                break
            asyncio.run(asyncio.sleep(0.05))
    with engine.connect() as conn:
        assert round(spent_total(conn), 2) == 0.40


def test_spending_survives_a_restart(engine: Engine) -> None:
    spend(engine, 0.85)
    with TestClient(app_for(engine)) as first:
        assert first.get("/play/status").json()["available"] is False
    with TestClient(app_for(engine)) as second:  # a new app over the same database
        assert second.get("/play/status").json()["available"] is False


def test_a_new_day_opens_play_again_but_the_total_remembers(engine: Engine) -> None:
    spend(engine, 1.00, "2026-10-28")
    with TestClient(app_for(engine)) as client:
        assert client.get("/play/status").json()["available"] is True


class Slow:
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.logs = [played(n) for n in (3, 4, 5)]
        self.used = 0

    async def __call__(
        self, seed: int, picks: Mapping[str, str], config: ApiSettings
    ) -> VisitorGame:
        log = self.logs[self.used]
        self.used += 1
        await self.release.wait()
        return VisitorGame("finished", log, Decimal("0"))


def test_games_in_flight_are_set_aside_so_the_cap_cannot_be_passed_by_starting_many(
    engine: Engine,
) -> None:
    app = app_for(engine, play_max_games=5)
    app.state.play_run = Slow()
    with TestClient(app) as client:
        first_three = [client.post("/play", json=BODY).status_code for _ in range(3)]
        fourth = client.post("/play", json=BODY)  # 3 x $0.30 in flight leaves $0.10 of $1.00
        assert first_three == [202, 202, 202]
        assert fourth.status_code == 429 and "right now" in fourth.json()["detail"]
        client.portal.call(app.state.play_run.release.set)  # type: ignore[union-attr]


def test_the_eleventh_request_in_a_minute_from_one_address_is_refused(engine: Engine) -> None:
    app = app_for(engine)
    now = [1000.0]
    app.state.play_clock = lambda: now[0]
    with TestClient(app) as client:
        codes = [client.post("/play", json=BAD).status_code for _ in range(10)]
        assert codes == [422] * 10
        limited = client.post("/play", json=BAD)
        assert limited.status_code == 429 and "minute" in limited.json()["detail"]
        now[0] += 61  # a minute later it is allowed again
        assert client.post("/play", json=BAD).status_code == 422


def test_the_rate_limit_is_a_setting(engine: Engine) -> None:
    app = app_for(engine, play_requests_per_minute=2)
    with TestClient(app) as client:
        assert [client.post("/play", json=BAD).status_code for _ in range(3)] == [422, 422, 429]


def test_a_game_is_given_the_per_game_budget_and_never_more(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, Decimal | None]] = []

    def build(model: str, max_spend: Decimal | None, **rest: object) -> object:
        seen.append((model, max_spend))
        raise RuntimeError("stop here: no key in a test")

    monkeypatch.setattr("werewolf.api.play.runtime.build_client", build)
    app = create_app(engine, settings().__class__(
        web_origin="http://site.test", cards_dir=REPO / "cards", play_model="gpt-4.1-mini",
        play_game_budget=Decimal("0.40"),
    ))  # fmt: skip
    app.state.play_day = lambda: TODAY
    with TestClient(app) as client:
        play_id = client.post("/play", json=BODY).json()["id"]
        for _ in range(100):
            if client.get(f"/play/{play_id}").json()["status"] != "running":
                break
            asyncio.run(asyncio.sleep(0.05))
    assert seen == [("gpt-4.1-mini", Decimal("0.40"))]


def test_the_status_says_how_many_games_are_left_today(engine: Engine) -> None:
    with TestClient(app_for(engine)) as client:
        assert client.get("/play/status").json() == {
            "available": True,
            "reason": "",
            "games_left": 3,
        }
    spend(engine, 0.40)  # $0.60 left
    with TestClient(app_for(engine)) as client:
        assert client.get("/play/status").json()["games_left"] == 2


def test_a_paused_play_mode_has_none_left_and_an_unset_one_says_nothing(engine: Engine) -> None:
    spend(engine, 0.90)
    with TestClient(app_for(engine)) as client:
        assert client.get("/play/status").json()["games_left"] == 0
    unset = create_app(engine, ApiSettings(web_origin="http://site.test", cards_dir=REPO / "cards"))
    with TestClient(unset) as client:
        assert client.get("/play/status").json()["games_left"] is None
