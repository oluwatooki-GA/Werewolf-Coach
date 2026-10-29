"""The read API: games, one replay, strategies, results and the coach's history."""

from pathlib import Path

import pytest
from api_support import VILLAGER_CARD, WOLF_CARD, build, played
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from werewolf.api.app import create_app
from werewolf.api.deps import ApiSettings, get_engine
from werewolf.engine.log import GameLog
from werewolf.tagger.adherence import wilson

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def logs() -> list[GameLog]:
    # seeds 1-4 have a wolf card and a villager card, 5-6 only a wolf card, 7 none
    with_both = [played(n, WOLF_CARD, VILLAGER_CARD) for n in (1, 2, 3, 4)]
    return [*with_both, played(5, WOLF_CARD), played(6, WOLF_CARD), played(7)]


@pytest.fixture
def client(tmp_path: Path, logs: list[GameLog]) -> TestClient:
    engine = build(tmp_path, logs, tagged=(1,))
    return TestClient(
        create_app(engine, ApiSettings(web_origin="http://site.test", cards_dir=REPO / "cards"))
    )


def test_health_is_ok_with_a_database_and_503_without_one(client: TestClient) -> None:
    assert client.get("/health").json()["database"] == "ok"  # more in test_ops.py
    broken = create_engine("sqlite:////no/such/folder/x.db")
    response = TestClient(create_app(broken)).get("/health")
    assert response.status_code == 503 and response.json()["database"] == "down"


def test_games_are_listed_with_a_total_and_can_be_paged_and_filtered(
    client: TestClient, logs: list[GameLog]
) -> None:
    body = client.get("/games").json()
    assert body["total"] == 7 and len(body["games"]) == 7
    first = body["games"][0]
    assert set(first) >= {"id", "seed", "winner", "rounds", "model", "cards", "cost"}
    assert set(first) >= {"rule_version", "status", "clean", "source"}
    assert "log" not in first  # the list stays small
    page = client.get("/games", params={"limit": 3, "offset": 5}).json()
    assert page["total"] == 7 and len(page["games"]) == 2
    wolves = sum(log.winner.value == "Wolves" for log in logs)
    assert client.get("/games", params={"winner": "Wolves"}).json()["total"] == wolves
    by_card = client.get("/games", params={"card": "villager.quiet_observer"}).json()
    assert by_card["total"] == 4


def test_a_bad_filter_is_422_and_an_unknown_game_is_404(client: TestClient) -> None:
    assert client.get("/games", params={"limit": 0}).status_code == 422
    assert client.get("/games", params={"winner": "Aliens"}).status_code == 422
    assert client.get("/games/nope").status_code == 404


def test_one_game_comes_with_its_whole_log_its_tags_and_the_derived_labels(
    client: TestClient, logs: list[GameLog]
) -> None:
    listed = client.get("/games", params={"limit": 200}).json()["games"]
    tagged = next(g for g in listed if g["seed"] == 1)
    body = client.get(f"/games/{tagged['id']}").json()
    assert GameLog.model_validate(body["game"]).to_json() == logs[0].to_json()
    assert body["tags"]["tags"][0]["moves"] == ["probe"]
    assert isinstance(body["derived"], list)
    plain = next(g for g in listed if g["seed"] == 7)
    assert client.get(f"/games/{plain['id']}").json()["tags"] is None


def test_strategies_lists_every_starter_card_with_its_text(client: TestClient) -> None:
    cards = {c["id"]: c for c in client.get("/strategies").json()}
    assert len(cards) >= 12
    card = cards["wolf.accuse_early"]
    assert card["version"] == 2 and card["role"] == "Werewolf" and "accuse" in card["instructions"]
    assert card["parent"] is None and card["expected_moves"]


def test_results_equal_a_hand_count_and_small_samples_say_not_clear_yet(
    client: TestClient, logs: list[GameLog]
) -> None:
    rows = {(r["card"], r["rule_version"]): r for r in client.get("/results").json()}
    wolf = rows[(WOLF_CARD, "v2")]
    wins = sum(log.winner.value == "Wolves" for log in logs[:6])  # games where a wolf had the card
    assert (wolf["games"], wolf["wins"]) == (6, wins)
    low, high = wilson(wins, 6)
    assert wolf["rate"] == pytest.approx(wins / 6)
    assert wolf["low"] == pytest.approx(low) and wolf["high"] == pytest.approx(high)
    assert wolf["role"] == "Werewolf" and wolf["enough"] is False
    village = rows[(VILLAGER_CARD, "v2")]
    assert village["games"] == 4
    assert village["wins"] == sum(log.winner.value == "Village" for log in logs[:4])


def test_the_coach_history_is_returned_by_side(client: TestClient) -> None:
    body = client.get("/coach/wolf").json()
    assert body["side"] == "wolf" and body["generations"][0]["number"] == 1
    assert body["generations"][0]["decision"] == "none played"
    assert client.get("/coach/villager").json()["generations"] == []
    assert client.get("/coach/seer").status_code == 404


def test_only_the_sites_own_origin_may_call_the_api_from_a_browser(client: TestClient) -> None:
    ok = client.get("/games", headers={"Origin": "http://site.test"})
    assert ok.headers["access-control-allow-origin"] == "http://site.test"
    other = client.get("/games", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in other.headers


def test_the_serve_command_runs_the_app_on_the_given_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    from werewolf.cli import main

    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(app=app, **kw))
    url = f"sqlite:///{tmp_path / 'serve.db'}"
    assert main(["app", "serve", "--database", url, "--host", "0.0.0.0", "--port", "8123"]) == 0
    assert (seen["host"], seen["port"]) == ("0.0.0.0", 8123)
    assert TestClient(seen["app"]).get("/health").status_code == 200  # type: ignore[arg-type]


def test_a_card_filter_matches_the_whole_id_and_treats_underscores_as_letters(
    client: TestClient,
) -> None:
    assert client.get("/games", params={"card": "wolf.accuse_early"}).json()["total"] == 6
    assert client.get("/games", params={"card": "wolf.accuse"}).json()["total"] == 0
    assert client.get("/games", params={"card": "wolf.accuseXearly"}).json()["total"] == 0


def test_paging_and_the_total_come_from_the_database(client: TestClient) -> None:
    seeds = [
        g["seed"] for g in client.get("/games", params={"limit": 3, "offset": 2}).json()["games"]
    ]
    assert seeds == [3, 4, 5]
    assert client.get("/games", params={"limit": 3, "offset": 2}).json()["total"] == 7


def test_every_answer_has_a_documented_shape(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("GameList", "GameDetail", "CardResult", "CoachHistory", "Health", "PlayStatus"):
        assert name in schemas, name


def test_the_database_can_be_swapped_with_a_dependency_override(
    client: TestClient, tmp_path: Path
) -> None:
    from werewolf.store import make_engine

    app = client.app
    app.dependency_overrides[get_engine] = lambda: make_engine(f"sqlite:///{tmp_path / 'empty.db'}")  # type: ignore[attr-defined]
    assert client.get("/games").json() == {"total": 0, "games": []}


def test_coach_runs_are_a_skeleton_that_says_so(client: TestClient) -> None:
    assert client.post("/coach/wolf/runs", json={}).status_code == 501
    assert client.get("/coach/runs/abc").status_code == 501


def test_games_can_be_filtered_to_ai_players_or_scripted_test_games(client: TestClient) -> None:
    # every game in this fixture is scripted (no model), so the AI filter finds none
    assert client.get("/games", params={"players": "scripted"}).json()["total"] == 7
    assert client.get("/games", params={"players": "ai"}).json()["total"] == 0
    assert client.get("/games", params={"players": "robots"}).status_code == 422
