"""Running it: /health says what is wrong without spending anything, /metrics counts from the
database, the admin page needs its token."""

import asyncio
from pathlib import Path

import pytest
from api_support import play_body
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings
from werewolf.store import make_engine
from werewolf.store.play import add_spend

REPO = Path(__file__).resolve().parents[2]
TODAY = "2026-10-29"


def settings(**more: object) -> ApiSettings:
    return ApiSettings(web_origin="http://site.test", cards_dir=REPO / "cards", **more)  # type: ignore[arg-type]


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return make_engine(f"sqlite:///{tmp_path / 'ops.db'}")


def app_for(engine: Engine, **more: object):  # type: ignore[no-untyped-def]
    app = create_app(engine, settings(**more))
    app.state.play_day = lambda: TODAY
    return app


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """/health must never call a model: any call in these tests is a failure."""

    async def forbidden(**kwargs: object) -> None:
        raise AssertionError("a paid call was made")

    monkeypatch.setattr("litellm.acompletion", forbidden)


# --- /health -----------------------------------------------------------------------------------


def test_health_with_play_not_set_up_is_ok_and_says_so(engine: Engine) -> None:
    with TestClient(app_for(engine)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "database": "ok",
            "provider": "off",
            "play": "off",
            "active_games": 0,
        }


def test_health_with_the_fake_model_has_play_open_and_no_provider_to_check(engine: Engine) -> None:
    with TestClient(app_for(engine, play_model="fake")) as client:
        body = client.get("/health").json()
        assert (body["provider"], body["play"], body["status"]) == ("off", "open", "ok")


def test_health_sees_the_providers_key_without_using_it(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with TestClient(app_for(engine, play_model="gpt-4o-mini")) as client:
        body = client.get("/health").json()
        assert (body["provider"], body["play"], body["status"]) == ("ok", "open", "ok")
        assert "sk-test" not in client.get("/health").text  # the key itself is never shown


def test_health_says_degraded_when_the_provider_key_is_missing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app_for(engine, play_model="gpt-4o-mini")) as client:
        response = client.get("/health")
        assert response.status_code == 200  # still serving replays, so not a reason to restart
        assert (response.json()["provider"], response.json()["status"]) == (
            "missing_key",
            "degraded",
        )


def test_health_says_play_is_paused_when_a_cap_is_used_up_but_stays_ok(engine: Engine) -> None:
    with engine.begin() as conn:
        add_spend(conn, TODAY, 0.95)
    with TestClient(app_for(engine, play_model="fake")) as client:
        body = client.get("/health").json()
        assert (body["play"], body["status"]) == ("paused", "ok")


def test_health_counts_the_games_being_played(engine: Engine) -> None:
    async def waits(*args: object) -> None:
        await asyncio.Event().wait()

    app = app_for(engine, play_model="fake")
    app.state.play_run = waits
    with TestClient(app) as client:
        assert client.post("/play", json=play_body()).status_code == 202
        assert client.get("/health").json()["active_games"] == 1


def test_health_is_503_when_the_database_cannot_be_reached() -> None:
    broken = create_engine("sqlite:////no/such/folder/x.db")
    response = TestClient(create_app(broken)).get("/health")
    assert response.status_code == 503
    assert (response.json()["status"], response.json()["database"]) == ("down", "down")


# --- /metrics ----------------------------------------------------------------------------------


def test_metrics_count_exactly_what_is_stored(tmp_path: Path) -> None:
    from api_support import build, played

    from werewolf.store.play import finish_session, new_session

    engine = build(tmp_path, [played(1), played(2), played(3)])
    with engine.begin() as conn:
        done = new_session(conn, {})
        finish_session(conn, done, "finished", game_id="1-x", cost=0.2)
        cut = new_session(conn, {})
        finish_session(conn, cut, "stopped", reason="budget", cost=0.1)
        add_spend(conn, "2026-10-28", 0.25)
        add_spend(conn, TODAY, 0.30)
    with TestClient(app_for(engine)) as client:
        with engine.begin() as conn:  # after start-up, which stops any game left running
            new_session(conn, {})
        body = client.get("/metrics").json()
    assert body["games"]["total"] == 3
    assert body["games"]["by_status"] == {"finished": 3}
    assert body["games"]["unclean"] == 0
    assert body["play"] == {"started": 3, "finished": 1, "stopped": 1, "running": 1}
    assert body["spend"]["today"] == pytest.approx(0.30)
    assert body["spend"]["total"] == pytest.approx(0.55)
    assert body["spend"]["by_day"] == {"2026-10-28": 0.25, TODAY: 0.30}


def test_metrics_see_a_game_that_was_played_here(engine: Engine) -> None:
    import time

    with TestClient(app_for(engine, play_model="fake")) as client:
        play_id = client.post("/play", json=play_body()).json()["id"]
        for _ in range(200):
            if client.get(f"/play/{play_id}").json()["status"] != "running":
                break
            time.sleep(0.05)
        body = client.get("/metrics").json()
    assert body["play"]["finished"] == 1 and body["play"]["running"] == 0
    assert body["games"]["by_source"] == {"play": 1}


def test_metrics_on_an_empty_database_are_zeros_not_errors(engine: Engine) -> None:
    with TestClient(app_for(engine)) as client:
        body = client.get("/metrics").json()
    assert body["games"] == {"total": 0, "by_status": {}, "by_source": {}, "unclean": 0}
    assert body["play"] == {"started": 0, "finished": 0, "stopped": 0, "running": 0}
    assert body["spend"] == {"today": 0.0, "total": 0.0, "by_day": {}}


def test_metrics_hold_no_secrets_and_no_visitor_data(engine: Engine) -> None:
    with TestClient(app_for(engine, play_model="fake")) as client:
        client.post("/play", json=play_body())
        text = client.get("/metrics").text
    assert "cards" not in text and "reason" not in text and "wolf.lie_low" not in text
