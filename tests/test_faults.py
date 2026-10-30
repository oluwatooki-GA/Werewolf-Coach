"""Fault switches: ways to make the model misbehave, so a game's failure paths are proven.
They exist only when APP_ENV=test, and never in a production process."""

import asyncio
import logging
from decimal import Decimal
from pathlib import Path

import pytest

from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.faults import FAULTS, FaultyTransport, active_faults, with_faults
from werewolf.llm.ledger import Ledger
from werewolf.llm.types import Completion, Request
from werewolf.play.service import play_visitor_game

SEED = 3
MODEL = "gpt-4o-mini"
TEST = {"APP_ENV": "test"}


class Base:
    """A model that is never reached in these tests: the switches stand in front of it."""

    def provider(self, model: str) -> str:
        return "openai"

    def estimate(self, request: Request) -> Decimal:
        return Decimal("0.05")  # a worst case, so one wasted answer (also $0.05) never beats it

    async def call(self, request: Request) -> Completion:
        raise AssertionError("the real model must not be called")


def client(tmp_path: Path, faults: list[str], budget: str | None = None) -> LLMClient:
    return LLMClient(
        FaultyTransport(Base(), faults),
        Ledger(tmp_path / "ledger.json"),
        FileCache(tmp_path / "cache"),
        run_budget=Decimal(budget) if budget else None,
    )


def play(tmp_path: Path, faults: list[str], budget: str | None = None):  # type: ignore[no-untyped-def]
    cards = {p.name: "default" for p in new_game(SEED).players}
    llm = client(tmp_path, faults, budget)
    return asyncio.run(play_visitor_game(SEED, cards, model=MODEL, client=llm))


def test_the_four_switches_have_names() -> None:
    assert set(FAULTS) == {"timeout", "bad_json", "never_ends", "retry_burn"}


def test_a_timeout_becomes_the_safe_default_and_the_game_still_ends(tmp_path: Path) -> None:
    game = play(tmp_path, ["timeout"])
    assert game.log is not None  # the game was played to its end, on defaults
    assert game.log.stats.failed_calls == len(game.log.calls) > 0
    assert game.log.rounds == 6 and game.log.winner.value == "Village"  # nobody died: round limit
    assert game.status == "stopped" and "was not a real game" in str(game.reason)  # and not shown


def test_broken_json_is_asked_again_once_and_then_defaulted(tmp_path: Path) -> None:
    game = play(tmp_path, ["bad_json"])
    assert game.log is not None
    assert all(call.failed and len(call.responses) == 2 for call in game.log.calls)
    assert game.status == "stopped"


def test_a_game_that_never_ends_stops_at_the_round_limit(tmp_path: Path) -> None:
    game = play(tmp_path, ["never_ends"])
    assert game.status == "finished" and game.log is not None
    assert game.log.rounds == game.log.settings.max_rounds == 6
    assert game.log.winner.value == "Village" and game.log.stats.failed_calls == 0
    # wolves were never killed and never killed anybody: the game just ran out of rounds
    assert not any(e.__class__.__name__ == "Removal" for e in game.log.events)


def test_a_retry_loop_is_stopped_by_the_run_budget(tmp_path: Path) -> None:
    game = play(tmp_path, ["retry_burn"], budget="0.12")
    assert game.status == "stopped" and game.log is None
    assert "run budget" in str(game.reason)
    assert Decimal("0") < game.cost <= Decimal("0.12")  # it spent, and stopped before the limit


def test_the_switches_can_be_combined(tmp_path: Path) -> None:
    transport = FaultyTransport(Base(), ["bad_json", "never_ends"])
    request = Request(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    done = asyncio.run(transport.call(request))
    assert done.text == "this is {not json"  # the first switch in the list wins


def test_no_real_provider_is_ever_reached_by_a_faulty_transport() -> None:
    transport = FaultyTransport(Base(), ["never_ends"])
    request = Request(model=MODEL, messages=[{"role": "user", "content": "hi"}])
    assert transport.provider(MODEL) == "openai" and transport.estimate(request) == Decimal("0.05")


# --- only in test mode -------------------------------------------------------------------------


def test_in_test_mode_the_switches_in_the_environment_wrap_the_transport() -> None:
    base = Base()
    wrapped = with_faults(base, {**TEST, "FAULTS": "timeout, bad_json"})
    assert isinstance(wrapped, FaultyTransport) and wrapped is not base


def test_with_no_switch_set_the_transport_is_left_alone() -> None:
    base = Base()
    assert with_faults(base, TEST) is base
    assert with_faults(base, {}) is base


@pytest.mark.parametrize("env", [{}, {"APP_ENV": "production"}, {"APP_ENV": "Test "}])
def test_outside_test_mode_a_switch_changes_nothing_and_is_warned_about(
    env: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    base = Base()
    with caplog.at_level(logging.WARNING, logger="werewolf.llm.faults"):
        assert with_faults(base, {**env, "FAULTS": "timeout"}) is base
    assert "FAULTS is set but APP_ENV is not 'test'" in caplog.text


def test_a_misspelled_switch_in_test_mode_is_an_error_not_a_silent_no_op() -> None:
    with pytest.raises(ValueError, match="unknown fault 'timeuot'"):
        with_faults(Base(), {**TEST, "FAULTS": "timeuot"})


def test_the_active_switches_are_named_only_in_test_mode() -> None:
    assert active_faults({**TEST, "FAULTS": "timeout,bad_json"}) == ["timeout", "bad_json"]
    assert active_faults({"FAULTS": "timeout"}) == []
    assert active_faults({"APP_ENV": "production", "FAULTS": "timeout"}) == []
    assert active_faults({}) == []


def test_a_client_built_for_a_run_picks_the_switches_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from werewolf.runtime import build_client

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("FAULTS", raising=False)
    plain = build_client(MODEL, Decimal("0.10"), root=tmp_path)
    assert not isinstance(plain._transport, FaultyTransport)  # type: ignore[attr-defined]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FAULTS", "timeout")
    faulty = build_client(MODEL, Decimal("0.10"), root=tmp_path)
    assert isinstance(faulty._transport, FaultyTransport)  # type: ignore[attr-defined]


def test_the_roles_at_the_test_table_are_what_these_tests_assume() -> None:
    roles = [p.role for p in new_game(SEED).players]
    assert roles.count(Role.WEREWOLF) == 2 and len(roles) == 8


# --- nothing of this reaches an image ----------------------------------------------------------


def test_the_image_and_the_compose_file_set_no_switch_and_no_test_mode() -> None:
    import yaml

    root = Path(__file__).resolve().parent.parent
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["api"]["environment"]
    assert "FAULTS" not in dockerfile and "APP_ENV" not in dockerfile
    assert "FAULTS" not in env and "APP_ENV" not in env
