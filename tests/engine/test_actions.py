import asyncio
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from werewolf.agents.scripted import ScriptedAgent, from_queue
from werewolf.engine.actions import (
    Action,
    BidAction,
    BidTask,
    ChatAction,
    NightTargetTask,
    TargetAction,
    Task,
    VoteAction,
    VoteTask,
    WolfChatTask,
)
from werewolf.engine.asking import Asked, ask, default_action
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.views import PlayerView, make_view


def view() -> PlayerView:
    return make_view(new_game(seed=1), "Ada")


def run(
    agent: ScriptedAgent,
    task: Task,
    check: Callable[[Action], str | None] | None = None,
) -> Asked:
    return asyncio.run(ask(agent, view(), task, check or (lambda action: None)))


BID_TASK = BidTask(max_bid=3, max_chars=300)


def test_a_valid_action_passes_through_unchanged() -> None:
    action = BidAction(bid=2, message="hello", intent="share_info")
    asked = run(from_queue([action]), BID_TASK)
    assert asked.action == action
    assert (asked.attempts, asked.rejected, asked.failed) == (1, 0, False)


def test_json_text_and_plain_dicts_are_accepted_and_checked_against_the_schema() -> None:
    from_text = run(from_queue(['{"bid": 1, "message": "hi", "intent": "ask"}']), BID_TASK)
    from_dict = run(from_queue([{"bid": 1, "message": "hi", "intent": "ask"}]), BID_TASK)
    assert from_text.action == from_dict.action == BidAction(bid=1, message="hi", intent="ask")


def test_a_schema_error_gets_one_retry_that_carries_the_error_text() -> None:
    seen: list[Task] = []

    def respond(v: PlayerView, task: Task) -> object:
        seen.append(task)
        return {"bid": "lots"} if task.error is None else {"bid": 1}

    asked = run(ScriptedAgent(respond), BID_TASK)
    assert asked.action == BidAction(bid=1)
    assert seen[0].error is None
    assert seen[1].error is not None and "bid" in seen[1].error
    assert (asked.attempts, asked.rejected, asked.failed) == (2, 1, False)


def test_an_illegal_move_gets_one_retry_that_carries_the_checkers_message() -> None:
    def check(action: Action) -> str | None:
        assert isinstance(action, BidAction)
        return "you only have 1 token left" if action.bid > 1 else None

    seen: list[Task] = []

    def respond(v: PlayerView, task: Task) -> object:
        seen.append(task)
        return BidAction(bid=3 if task.error is None else 1)

    asked = run(ScriptedAgent(respond), BID_TASK, check)
    assert seen[1].error == "you only have 1 token left"
    assert asked.action == BidAction(bid=1)
    assert asked.rejected == 1


def test_two_failures_use_the_safe_default_and_count_as_a_failure() -> None:
    asked = run(from_queue([{"bid": 99, "x": 1}, "not json"]), BID_TASK, lambda a: "no")
    assert asked.action == BidAction(bid=0)
    assert (asked.attempts, asked.rejected, asked.failed) == (2, 2, True)


def test_an_agent_that_raises_is_handled_like_a_bad_answer() -> None:
    def respond(v: PlayerView, task: Task) -> object:
        raise RuntimeError("model timed out")

    asked = run(ScriptedAgent(respond), BID_TASK)
    assert asked.action == BidAction(bid=0)
    assert (asked.rejected, asked.failed) == (2, True)
    assert "model timed out" in asked.errors[0]


def test_the_wrong_kind_of_action_is_rejected() -> None:
    asked = run(from_queue([VoteAction(target="Bo", reason="x"), BidAction(bid=1)]), BID_TASK)
    assert asked.action == BidAction(bid=1)
    assert asked.rejected == 1


def test_every_raw_response_is_recorded_in_order() -> None:
    asked = run(from_queue([{"bid": "lots"}, BidAction(bid=2)]), BID_TASK)
    assert asked.responses == [{"bid": "lots"}, BidAction(bid=2).model_dump(mode="json")]


def test_a_recorded_exception_marker_replays_with_the_same_error_text() -> None:
    def boom(v: PlayerView, task: Task) -> object:
        raise RuntimeError("model timed out")

    first = run(ScriptedAgent(boom), BID_TASK)
    replayed = run(from_queue(first.responses), BID_TASK)
    assert replayed.errors == first.errors
    assert replayed.action == first.action


def test_each_kind_of_task_has_a_safe_default() -> None:
    assert default_action(WolfChatTask(max_chars=300)) == ChatAction(text="")
    night = NightTargetTask(purpose="check", options=("Bo",))
    assert default_action(night) == TargetAction(target=None)
    assert default_action(BID_TASK) == BidAction(bid=0)
    assert default_action(VoteTask(options=("Bo",))) == VoteAction(target=None, reason="")


def test_a_negative_bid_fails_the_schema() -> None:
    with pytest.raises(ValidationError):
        BidAction(bid=-1)


def test_actions_may_carry_a_private_note_and_beliefs() -> None:
    action = BidAction.model_validate(
        {"bid": 1, "note": "Bo is quiet", "beliefs": {"Bo": {"suspicion": 0.7, "reason": "quiet"}}}
    )
    assert action.beliefs["Bo"].suspicion == 0.7
    with pytest.raises(ValidationError):
        BidAction.model_validate({"bid": 1, "beliefs": {"Bo": {"suspicion": 1.5}}})


def test_the_view_a_scripted_agent_sees_is_a_player_view() -> None:
    got: list[object] = []

    def respond(v: PlayerView, task: Task) -> object:
        got.append(v)
        return BidAction(bid=0)

    run(ScriptedAgent(respond), BID_TASK)
    assert isinstance(got[0], PlayerView)
    assert got[0].role in Role
