"""The conversation layout: one chat per player per round, each question adds only what is new."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from test_cli_llm import MODEL, install
from test_llm_agent import Rig

from werewolf.agents.wire import to_action_json, to_wire_json
from werewolf.audit import find_leaks
from werewolf.cli import main
from werewolf.engine.log import GameLog
from werewolf.llm.transport import _mark_for_cache
from werewolf.promptview import rebuild

Prompts = list[list[dict[str, str]]]

WIRE = {
    "wolf_chat": {"text": "Take Eve", "note": "she is sharp"},
    "night_target": {"target": "", "note": "nobody"},
    "bid": {
        "bid": 2,
        "message": "Bo, why?",
        "intent": "ask",
        "target": "Bo",
        "note": "n",
        "beliefs": [{"player": "Bo", "suspicion": 0.6, "reason": "r"}],
        "cites": [{"line": "R1-2", "speaker": "Bo"}],
    },
    "vote": {
        "target": "Bo",
        "reason": "dodged",
        "note": "n",
        "beliefs": [{"player": "Bo", "suspicion": 0.7, "reason": "r"}],
    },
    "memory": {"summary": "Bo seems honest"},
}


def play_chat_game(tmp_path: Path) -> tuple[Rig, GameLog]:
    rig = Rig(tmp_path)
    rig.model.raw["WireBid"] = json.dumps(
        {
            "bid": 1,
            "message": "hello table",
            "intent": "none",
            "target": "",
            "note": "n",
            "beliefs": [],
            "cites": [],
        }
    )
    return rig, rig.play(layout="conversation", summarize=True)


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> tuple[Rig, GameLog]:
    return play_chat_game(tmp_path_factory.mktemp("chat"))


def chats(rig: Rig) -> dict[str, list[Prompts]]:
    """Each player's prompts in order, grouped into chats (a new chat has no assistant turn)."""
    found: dict[str, list[Prompts]] = {}
    for name, messages in rig.prompts:
        lists = found.setdefault(name, [])
        if not lists or not any(m["role"] == "assistant" for m in messages):
            lists.append([])
        lists[-1].append(messages)
    return found


@pytest.mark.parametrize("kind", sorted(WIRE))
def test_an_accepted_answer_converts_to_the_model_shape_and_back(kind: str) -> None:
    action = to_action_json(kind, json.dumps(WIRE[kind]))
    shown = to_wire_json(kind, action)
    assert json.loads(shown) == WIRE[kind] and to_action_json(kind, shown) == action


def test_every_prompt_starts_with_the_previous_one_and_that_answer(
    game: tuple[Rig, GameLog],
) -> None:
    rig, _ = game
    steps = 0
    for per_player in chats(rig).values():
        for chat in per_player:
            for before, after in zip(chat, chat[1:], strict=False):
                assert after[: len(before)] == before
                assert [m["role"] for m in after[len(before) :]] == ["assistant", "user"]
                steps += 1
    assert steps > 50  # a real game, not a trivial pass


def test_a_chat_starts_with_the_whole_picture_and_continues_with_only_what_is_new(
    game: tuple[Rig, GameLog],
) -> None:
    rig, _ = game
    for per_player in chats(rig).values():
        for chat in per_player:
            assert "## What has happened" in chat[0][1]["content"]
            last = chat[-1]
            assert sum("## What has happened" in m["content"] for m in last) == 1
            assert all("## What has happened" not in m["content"] for m in last[2:])


def test_the_belief_table_is_not_repeated_because_the_earlier_answers_are_in_the_chat(
    game: tuple[Rig, GameLog],
) -> None:
    rig, _ = game
    assert all("Your suspicions" not in m["content"] for _, msgs in rig.prompts for m in msgs)


def test_a_new_round_starts_a_new_chat_that_carries_the_summary(game: tuple[Rig, GameLog]) -> None:
    rig, _ = game
    second_round = [
        chat[0][1]["content"]
        for per_player in chats(rig).values()
        for chat in per_player[1:]
        if "Round 2." in chat[0][-1]["content"]
    ]
    assert second_round and all("Summary of earlier rounds" in text for text in second_round)
    assert all("## Game record" in text for text in second_round)


def test_a_rejected_answer_is_followed_by_the_error_in_the_same_chat(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.model.raw["WireBid"] = '{"bid": "lots"}'  # never readable, so every bid is retried
    rig.play(layout="conversation")
    retries = [m for _, m in rig.prompts if m[-1]["content"].startswith("Your last answer")]
    assert retries
    asked, answer, error = retries[0][-3:]
    assert (asked["role"], answer["role"], error["role"]) == ("user", "assistant", "user")
    assert answer["content"] == '{"bid": "lots"}'


def test_a_player_sees_its_own_notes_and_nobody_elses(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.model.plant = True
    rig.model.kill_last = True
    log = rig.play(seed=1, layout="conversation", summarize=True)
    own = 0
    for name, messages in rig.prompts:
        text = "\n".join(m["content"] for m in messages)
        for author in re.findall(r"SECRET-NOTE-\w+-(\w+)-\d+", text):
            assert author == name
            own += 1
    assert own > 0  # the notes really are in the chat
    assert find_leaks(log, rig.prompts, own_notes_ok=True) == []


def test_rebuilt_prompts_equal_the_prompts_the_players_were_sent(
    game: tuple[Rig, GameLog],
) -> None:
    rig, log = game
    items = rebuild(log, layout="conversation")
    for player in {p.name for p in log.players}:
        sent = [m for name, m in rig.prompts if name == player]
        assert [i.messages for i in items if i.player == player] == sent


def test_only_the_system_message_is_marked_unless_the_chat_tail_is_asked_for() -> None:
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "u2"},
    ]
    marked = [isinstance(m["content"], list) for m in _mark_for_cache(messages, tail=False)]
    assert marked == [True, False, False, False]
    marked = [isinstance(m["content"], list) for m in _mark_for_cache(messages, tail=True)]
    assert marked == [True, False, False, True]


def test_a_batch_in_the_conversation_layout_plays_and_the_audit_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path / "rig")
    install(rig, monkeypatch, [])
    args = ["batch", "--model", MODEL, "--max-spend", str(Decimal("1.00")), "--games", "1"]
    code = main([*args, "--layout", "conversation", "--data-dir", str(tmp_path / "games")])
    assert code == 0 and "leaks: 0" in capsys.readouterr().out
    assert any(
        any(m["role"] == "assistant" for m in call.messages) for call in rig.model.calls
    )  # and it really used chats
