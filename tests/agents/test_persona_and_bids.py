"""Seeded table manners, and the count of bids per game."""

import json
from collections import Counter
from pathlib import Path

import pytest
from test_cli_llm import MODEL, install
from test_llm_agent import Rig, player_of
from test_prompt import BID, state_with

from werewolf.agents.persona import PERSONAS, assign, describe
from werewolf.agents.prompt import build_messages
from werewolf.cli import main
from werewolf.engine.events import Speech
from werewolf.engine.log import GameLog, replays_exactly
from werewolf.engine.state import Settings
from werewolf.engine.views import make_view
from werewolf.promptview import rebuild
from werewolf.runner import BatchReport, Played, bid_counts, bid_text, format_game, format_report
from werewolf.transcript import render

NAMES = Settings().names


def bid_calls(log: GameLog) -> int:
    """Calls where a player really chose a bid."""
    return sum(
        c.task["kind"] == "bid" and not c.task.get("free") and c.task["max_bid"] > 0
        for c in log.calls
    )


def bidding_game(tmp_path: Path, answer: str) -> GameLog:
    rig = Rig(tmp_path)
    rig.model.raw["WireBid"] = answer
    return rig.play(seed=1)


TWO = json.dumps(
    {
        "bid": 2,
        "message": "hello table",
        "intent": "none",
        "target": "",
        "note": "n",
        "beliefs": [],
        "cites": [],
    }
)


def test_every_player_gets_a_manner_spread_as_evenly_as_eight_allow() -> None:
    manners = assign(1, NAMES)
    assert set(manners) == set(NAMES) and set(manners.values()) == set(PERSONAS)
    assert sorted(Counter(manners.values()).values()) == [2, 3, 3]


def test_the_same_seed_gives_the_same_manners_and_other_seeds_shuffle_them() -> None:
    assert assign(5, NAMES) == assign(5, NAMES)
    assert len({tuple(assign(seed, NAMES).items()) for seed in range(10)}) > 1


def test_the_manner_is_one_short_line_in_the_system_message_only_when_given() -> None:
    view = make_view(state_with(), "Cy")
    with_manner = build_messages(view, BID, persona="chatty")
    plain = build_messages(view, BID)
    assert f"Table manner: {describe('chatty')}" in with_manner[0]["content"]
    assert "Table manner" not in plain[0]["content"]
    assert with_manner[1] == plain[1]  # nothing else about the prompt changes


def test_a_log_without_personas_keeps_its_old_settings_shape() -> None:
    assert "personas" not in Settings().model_dump(mode="json")
    shown = Settings(personas={"Bo": "blunt"}).model_dump(mode="json")
    assert shown["personas"] == {"Bo": "blunt"}


def played_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str
) -> tuple[Rig, GameLog]:
    rig = Rig(tmp_path / "rig")
    install(rig, monkeypatch, [])
    args = ["batch", "--model", MODEL, "--max-spend", "1.00", "--games", "1", "--first-seed", "3"]
    assert main([*args, *extra, "--data-dir", str(tmp_path / "games")]) == 0
    (path,) = (tmp_path / "games").glob("*.json")
    return rig, GameLog.from_json(path.read_text(encoding="utf-8"))


def test_a_batch_gives_each_player_its_seeded_manner_and_logs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, log = played_batch(tmp_path, monkeypatch)
    assert log.settings.personas == assign(3, log.settings.names)
    for call in rig.model.calls:
        manner = log.settings.personas[player_of(call)]
        assert f"Table manner: {describe(manner)}" in call.messages[0]["content"]
    assert replays_exactly(log)


def test_no_persona_leaves_the_prompts_and_the_log_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, log = played_batch(tmp_path, monkeypatch, "--no-persona")
    assert log.settings.personas == {}
    assert all("Table manner" not in c.messages[0]["content"] for c in rig.model.calls)


def test_the_rebuilt_prompts_and_the_private_view_show_the_manner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, log = played_batch(tmp_path, monkeypatch)
    for item in rebuild(log):
        manner = log.settings.personas[item.player]
        assert f"Table manner: {describe(manner)}" in item.messages[0]["content"]
    private = render(log, private=True).splitlines()[1]
    assert all(f"{n}=" in private and f"({m})" in private for n, m in log.settings.personas.items())
    assert "(" not in render(log).splitlines()[1]  # the public view says nothing about it


def test_every_bid_a_player_chose_is_counted_and_so_is_each_winning_bid(tmp_path: Path) -> None:
    log = bidding_game(tmp_path, TWO)
    chosen, won = bid_counts([log])
    assert sum(chosen.values()) == bid_calls(log) > 0
    assert set(chosen) <= {0, 2} and chosen[2] > 0  # a bid of 2 with 1 token left falls back to 0
    posted = [e for e in log.events if isinstance(e, Speech) and not e.reply]
    assert sum(won.values()) == len(posted) and set(won) == {2}


def test_a_bid_that_fell_back_counts_as_zero(tmp_path: Path) -> None:
    log = bidding_game(tmp_path, '{"bid": "lots"}')  # never readable, so every bid falls back
    chosen, won = bid_counts([log])
    assert chosen == Counter({0: bid_calls(log)}) and not won


def test_the_bid_text_lists_sizes_and_the_report_and_game_line_carry_it(tmp_path: Path) -> None:
    log = bidding_game(tmp_path, TWO)
    chosen, won = bid_counts([log])
    sizes = " ".join(f"{s}:{chosen[s]}" for s in sorted(chosen))
    wins = " ".join(f"{s}:{won[s]}" for s in sorted(won))
    assert bid_text([log]) == f"bids {sizes} (won the floor with {wins})"
    played = Played(1, "run", log, 1.0, [], tmp_path / "x.json")
    assert f"  {bid_text([log])}\n" in format_game(played)
    assert bid_text([log]) in format_report(BatchReport(played=[played]))


def test_a_silent_game_has_no_winning_bids(tmp_path: Path) -> None:
    log = Rig(tmp_path).play(seed=1)  # the fake model only ever listens
    assert bid_text([log]).endswith("(won the floor with none)")
    assert bid_counts([log])[0] == Counter({0: bid_calls(log)})
