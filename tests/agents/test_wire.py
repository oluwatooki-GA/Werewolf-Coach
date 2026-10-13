import json
from typing import Any

import pytest

from werewolf.agents.wire import (
    NOTE_MAX,
    REASON_MAX,
    WIRE_FOR,
    WireError,
    json_schema_for,
    to_action_json,
)
from werewolf.engine.actions import ACTION_FOR, BidAction, ChatAction, TargetAction, VoteAction

KINDS = list(WIRE_FOR)
UNSUPPORTED = {"maxLength", "minLength", "minimum", "maximum", "pattern", "format", "default"}


def resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        return schema["$defs"][node["$ref"].split("/")[-1]]
    return node


def objects(schema: dict[str, Any], node: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every object schema inside this schema, following references."""
    node = resolve(schema, node if node is not None else schema)
    found = [node] if node.get("type") == "object" else []
    for child in node.get("properties", {}).values():
        found += objects(schema, child)
    if "items" in node:
        found += objects(schema, node["items"])
    return found


def keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


@pytest.mark.parametrize("kind", KINDS)
def test_every_object_is_closed_and_every_property_required(kind: str) -> None:
    schema = json_schema_for(kind)
    found = objects(schema)
    assert found
    for obj in found:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


@pytest.mark.parametrize("kind", KINDS)
def test_no_keyword_that_strict_mode_may_refuse(kind: str) -> None:
    assert not (keys(json_schema_for(kind)["properties"]) & UNSUPPORTED)


@pytest.mark.parametrize("kind", KINDS)
def test_there_are_no_free_key_objects(kind: str) -> None:
    schema = json_schema_for(kind)
    assert all("properties" in obj for obj in objects(schema))


WIRE_EXAMPLES: dict[str, dict[str, Any]] = {
    "wolf_chat": {"text": "Let us take Bo.", "note": "Bo asks too many questions"},
    "night_target": {"target": "Bo", "note": "likely the Seer"},
    "bid": {
        "bid": 2,
        "message": "Cy has been very quiet.",
        "intent": "accuse",
        "target": "Cy",
        "note": "Cy never speaks",
        "beliefs": [
            {"player": "Cy", "suspicion": 0.8, "reason": "silent"},
            {"player": "Bo", "suspicion": 0.2, "reason": "open"},
        ],
    },
    "vote": {"target": "Cy", "reason": "quiet and dodgy", "note": "n", "beliefs": []},
}


@pytest.mark.parametrize("kind", list(WIRE_EXAMPLES))
def test_converted_output_is_a_valid_engine_action(kind: str) -> None:
    converted = to_action_json(kind, json.dumps(WIRE_EXAMPLES[kind]))
    action = ACTION_FOR[kind].model_validate_json(converted)
    assert isinstance(action, ChatAction | TargetAction | BidAction | VoteAction)


def test_beliefs_become_a_table_keyed_by_player() -> None:
    action = BidAction.model_validate_json(to_action_json("bid", json.dumps(WIRE_EXAMPLES["bid"])))
    assert action.beliefs["Cy"].suspicion == 0.8 and action.beliefs["Bo"].reason == "open"
    assert (action.bid, action.intent, action.target) == (2, "accuse", "Cy")


def test_none_and_empty_become_null() -> None:
    wire = dict(WIRE_EXAMPLES["bid"], intent="none", target="", bid=0, message="")
    action = BidAction.model_validate_json(to_action_json("bid", json.dumps(wire)))
    assert action.intent is None and action.target is None
    target = TargetAction.model_validate_json(
        to_action_json("night_target", json.dumps({"target": "", "note": ""}))
    )
    assert target.target is None


def test_suspicion_is_clamped_to_the_range_a_belief_allows() -> None:
    wire = dict(WIRE_EXAMPLES["vote"], beliefs=[{"player": "Bo", "suspicion": 1.7, "reason": "x"}])
    action = VoteAction.model_validate_json(to_action_json("vote", json.dumps(wire)))
    assert action.beliefs["Bo"].suspicion == 1.0


def test_long_private_text_is_cut_to_its_cap() -> None:
    wire = dict(
        WIRE_EXAMPLES["bid"],
        note="n" * 500,
        beliefs=[{"player": "Cy", "suspicion": 0.5, "reason": "r" * 500}],
    )
    action = BidAction.model_validate_json(to_action_json("bid", json.dumps(wire)))
    assert len(action.note) == NOTE_MAX
    assert len(action.beliefs["Cy"].reason) == REASON_MAX


def test_a_message_is_not_cut_so_the_engine_can_reject_it() -> None:
    wire = dict(WIRE_EXAMPLES["bid"], message="m" * 400)
    action = BidAction.model_validate_json(to_action_json("bid", json.dumps(wire)))
    assert len(action.message) == 400


def test_a_repeated_player_in_beliefs_keeps_the_last_entry() -> None:
    wire = dict(
        WIRE_EXAMPLES["vote"],
        beliefs=[
            {"player": "Bo", "suspicion": 0.1, "reason": "a"},
            {"player": "Bo", "suspicion": 0.9, "reason": "b"},
        ],
    )
    action = VoteAction.model_validate_json(to_action_json("vote", json.dumps(wire)))
    assert action.beliefs["Bo"].suspicion == 0.9


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"bid": "lots"}',
        json.dumps({k: v for k, v in WIRE_EXAMPLES["bid"].items() if k != "message"}),
        json.dumps(dict(WIRE_EXAMPLES["bid"], surprise=1)),
        json.dumps(dict(WIRE_EXAMPLES["bid"], intent="shout")),
    ],
)
def test_bad_output_raises_a_clear_error(text: str) -> None:
    with pytest.raises(WireError) as caught:
        to_action_json("bid", text)
    assert str(caught.value)


def test_an_unknown_task_kind_is_an_error() -> None:
    with pytest.raises(WireError, match="unknown task kind"):
        to_action_json("dance", "{}")


def longest(kind: str) -> str:
    belief = {"player": "Eve", "suspicion": 0.55, "reason": "r" * REASON_MAX}
    full: dict[str, Any] = {
        "wolf_chat": {"text": "t" * 300, "note": "n" * NOTE_MAX},
        "night_target": {"target": "Eve", "note": "n" * NOTE_MAX},
        "bid": {
            "bid": 3,
            "message": "m" * 300,
            "intent": "share_info",
            "target": "Eve",
            "note": "n" * NOTE_MAX,
            "beliefs": [belief] * 7,
        },
        "vote": {
            "target": "Eve",
            "reason": "v" * 150,
            "note": "n" * NOTE_MAX,
            "beliefs": [belief] * 7,
        },
    }
    return json.dumps(full[kind], separators=(",", ":"))


@pytest.mark.parametrize("kind", ["wolf_chat", "night_target", "bid", "vote"])
def test_the_longest_allowed_answer_fits_in_300_tokens(kind: str) -> None:
    assert len(longest(kind)) // 4 <= 300  # a rough count: characters divided by 4


def test_a_memory_summary_is_converted_as_it_is() -> None:
    assert json.loads(to_action_json("memory", '{"summary": "Round 1: Bo died."}')) == {
        "summary": "Round 1: Bo died."
    }
