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
            "faults": [],
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


def test_health_names_the_fault_switches_that_are_on_so_production_can_be_checked(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAULTS", "timeout,bad_json")
    monkeypatch.delenv("APP_ENV", raising=False)
    with TestClient(app_for(engine)) as client:
        assert client.get("/health").json()["faults"] == []  # set, but not a test process: off
    monkeypatch.setenv("APP_ENV", "test")
    with TestClient(app_for(engine)) as client:
        assert client.get("/health").json()["faults"] == ["timeout", "bad_json"]


def test_health_is_503_when_the_database_cannot_be_reached(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")  # a database cannot live inside a file
    broken = create_engine(f"sqlite:///{blocker / 'x.db'}")
    response = TestClient(create_app(broken)).get("/health")
    assert response.status_code == 503
    assert (response.json()["status"], response.json()["database"]) == ("down", "down")


# --- /metrics ----------------------------------------------------------------------------------

TOKEN = "s3cret-admin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_metrics_do_not_exist_without_a_token_set_and_need_it_when_set(engine: Engine) -> None:
    with TestClient(app_for(engine)) as client:
        assert client.get("/metrics").status_code == 404
        assert client.get("/metrics", headers=AUTH).status_code == 404
    with TestClient(app_for(engine, admin_token=TOKEN)) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/metrics", headers=AUTH).status_code == 200


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
    with TestClient(app_for(engine, admin_token=TOKEN)) as client:
        with engine.begin() as conn:  # after start-up, which stops any game left running
            new_session(conn, {})
        body = client.get("/metrics", headers=AUTH).json()
    assert body["games"]["total"] == 3
    assert body["games"]["by_status"] == {"finished": 3}
    assert body["games"]["unclean"] == 0
    assert body["play"] == {"started": 3, "finished": 1, "stopped": 1, "running": 1}
    assert body["spend"]["today"] == pytest.approx(0.30)
    assert body["spend"]["total"] == pytest.approx(0.55)
    assert body["spend"]["by_day"] == {"2026-10-28": 0.25, TODAY: 0.30}


def test_metrics_see_a_game_that_was_played_here(engine: Engine) -> None:
    import time

    with TestClient(app_for(engine, play_model="fake", admin_token=TOKEN)) as client:
        play_id = client.post("/play", json=play_body()).json()["id"]
        for _ in range(200):
            if client.get(f"/play/{play_id}").json()["status"] != "running":
                break
            time.sleep(0.05)
        body = client.get("/metrics", headers=AUTH).json()
    assert body["play"]["finished"] == 1 and body["play"]["running"] == 0
    assert body["games"]["by_source"] == {"play": 1}


def test_metrics_on_an_empty_database_are_zeros_not_errors(engine: Engine) -> None:
    with TestClient(app_for(engine, admin_token=TOKEN)) as client:
        body = client.get("/metrics", headers=AUTH).json()
    assert body["games"] == {"total": 0, "by_status": {}, "by_source": {}, "unclean": 0}
    assert body["play"] == {"started": 0, "finished": 0, "stopped": 0, "running": 0}
    assert body["spend"] == {"today": 0.0, "total": 0.0, "by_day": {}}


def test_metrics_hold_no_secrets_and_no_visitor_data(engine: Engine) -> None:
    with TestClient(app_for(engine, play_model="fake", admin_token=TOKEN)) as client:
        client.post("/play", json=play_body())
        text = client.get("/metrics", headers=AUTH).text
    assert "cards" not in text and "reason" not in text and "wolf.lie_low" not in text


# --- logs --------------------------------------------------------------------------------------


def test_a_game_played_here_writes_json_lines_that_all_carry_its_id(engine: Engine) -> None:
    import io
    import json
    import logging
    import time

    from werewolf.logs import JsonFormatter

    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("werewolf.api.play")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        with TestClient(app_for(engine, play_model="fake")) as client:
            play_id = client.post("/play", json=play_body()).json()["id"]
            for _ in range(200):
                state = client.get(f"/play/{play_id}").json()
                if state["status"] != "running":
                    break
                time.sleep(0.05)
    finally:
        log.removeHandler(handler)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [line["message"] for line in lines] == ["play started", "play finished"]
    assert all(line["play_id"] == play_id for line in lines)
    done = lines[-1]
    assert done["status"] == "finished" and done["cost"] == 0.0
    assert done["game_id"] == state["game_id"]  # the id the replay opens with
    assert "wolf.lie_low" not in out.getvalue()  # what the visitor picked is not logged


def test_a_game_that_stops_logs_why(engine: Engine) -> None:
    import io
    import json
    import logging
    import time
    from decimal import Decimal

    from werewolf.logs import JsonFormatter
    from werewolf.play.service import VisitorGame

    async def stops(*args: object) -> VisitorGame:
        return VisitorGame("stopped", None, Decimal("0.2"), reason="the run budget is used up")

    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("werewolf.api.play")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    app = app_for(engine, play_model="fake")
    app.state.play_run = stops
    try:
        with TestClient(app) as client:
            play_id = client.post("/play", json=play_body()).json()["id"]
            for _ in range(200):
                if client.get(f"/play/{play_id}").json()["status"] != "running":
                    break
                time.sleep(0.05)
    finally:
        log.removeHandler(handler)
    last = json.loads(out.getvalue().splitlines()[-1])
    assert last["message"] == "play stopped" and last["reason"] == "the run budget is used up"
    assert last["cost"] == 0.2


# --- admin -------------------------------------------------------------------------------------


def test_admin_does_not_exist_unless_a_token_is_set(engine: Engine) -> None:
    with TestClient(app_for(engine)) as client:
        assert client.get("/admin/overview").status_code == 404
        assert (
            client.get("/admin/overview", headers={"Authorization": "Bearer "}).status_code == 404
        )


def test_admin_needs_the_token(engine: Engine) -> None:
    with TestClient(app_for(engine, admin_token=TOKEN)) as client:
        assert client.get("/admin/overview").status_code == 401
        for wrong in (f"Bearer {TOKEN}x", "Bearer wrong", TOKEN, "Basic " + TOKEN, "Bearer"):
            response = client.get("/admin/overview", headers={"Authorization": wrong})
            assert response.status_code == 401, wrong
        assert TOKEN not in client.get("/admin/overview").text
        ok = client.get("/admin/overview", headers={"Authorization": f"Bearer {TOKEN}"})
        assert ok.status_code == 200


def test_admin_shows_the_counts_and_the_latest_games_played_here(engine: Engine) -> None:
    import time

    with TestClient(app_for(engine, admin_token=TOKEN, play_model="fake")) as client:
        for _ in range(2):
            play_id = client.post("/play", json=play_body()).json()["id"]
            for _ in range(200):
                if client.get(f"/play/{play_id}").json()["status"] != "running":
                    break
                time.sleep(0.05)
        body = client.get("/admin/overview", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert body["metrics"]["play"]["finished"] == 2
    assert body["play_model"] == "fake" and body["active_games"] == 0
    assert [p["status"] for p in body["recent"]] == ["finished", "finished"]
    assert set(body["recent"][0]) == {"id", "status", "reason", "cost", "created_at", "game_id"}
    assert body["recent"][0]["created_at"] >= body["recent"][1]["created_at"]  # newest first


def test_admin_lists_at_most_the_latest_twenty(engine: Engine) -> None:
    from werewolf.store.play import new_session

    with TestClient(app_for(engine, admin_token=TOKEN)) as client:
        with engine.begin() as conn:
            for _ in range(25):
                new_session(conn, {})
        body = client.get("/admin/overview", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert len(body["recent"]) == 20
