"""The shape the model fills in, and its conversion to the engine's action JSON.

Strict structured-output modes need closed objects with every field required and no free-key
dicts, so the belief table is a list here and "nothing" is spelled "none" or "". `to_action_json`
turns that into the engine's own action format, which the engine then checks itself.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

NOTE_MAX = 100  # private note, in characters (cut, not rejected)
REASON_MAX = 40  # reason on one belief or one vote line
SUMMARY_MAX = 800


class WireError(ValueError):
    """The model's output could not be read as the answer this task needs."""


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WireBelief(_Wire):
    player: str
    suspicion: float
    reason: str


class WireCite(_Wire):
    line: str  # such as "R2-4"
    speaker: str  # the player who wrote that line


class WireChat(_Wire):
    text: str
    note: str


class WireTarget(_Wire):
    target: str  # "" means no target
    note: str


class WireBid(_Wire):
    bid: int
    message: str
    intent: Literal["accuse", "defend", "share_info", "ask", "none"]
    target: str  # "" means none
    note: str
    beliefs: list[WireBelief]
    cites: list[WireCite] = []  # optional when reading an answer; the schema still lists it


class WireVote(_Wire):
    target: str  # "" means abstain
    reason: str
    note: str
    beliefs: list[WireBelief]


class WireMemory(_Wire):
    summary: str


WIRE_FOR: dict[str, type[_Wire]] = {
    "wolf_chat": WireChat,
    "night_target": WireTarget,
    "bid": WireBid,
    "vote": WireVote,
    "memory": WireMemory,
}


def json_schema_for(kind: str) -> dict[str, Any]:
    schema = WIRE_FOR[kind].model_json_schema()
    schema["required"] = list(schema["properties"])  # strict mode wants every field required
    for field in schema["properties"].values():
        field.pop("default", None)  # and refuses "default"
    return schema


def _beliefs(items: list[WireBelief]) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for item in items:  # a repeated player keeps its last entry
        suspicion = min(1.0, max(0.0, item.suspicion))
        table[item.player] = {"suspicion": suspicion, "reason": item.reason[:REASON_MAX]}
    return table


def to_action_json(kind: str, text: str) -> str:
    model = WIRE_FOR.get(kind)
    if model is None:
        raise WireError(f"unknown task kind '{kind}'")
    try:
        wire = model.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "answer"
        raise WireError(f"{where}: {first['msg']}") from exc

    action: dict[str, Any]
    if isinstance(wire, WireChat):
        action = {"text": wire.text, "note": wire.note[:NOTE_MAX]}
    elif isinstance(wire, WireTarget):
        action = {"target": wire.target or None, "note": wire.note[:NOTE_MAX]}
    elif isinstance(wire, WireBid):
        action = {
            "bid": wire.bid,
            "message": wire.message,
            "intent": None if wire.intent == "none" else wire.intent,
            "target": wire.target or None,
            "note": wire.note[:NOTE_MAX],
            "beliefs": _beliefs(wire.beliefs),
            "cites": [{"line": c.line, "speaker": c.speaker} for c in wire.cites],
        }
    elif isinstance(wire, WireVote):
        action = {
            "target": wire.target or None,
            "reason": wire.reason,
            "note": wire.note[:NOTE_MAX],
            "beliefs": _beliefs(wire.beliefs),
        }
    else:
        assert isinstance(wire, WireMemory)
        action = {"summary": wire.summary[:SUMMARY_MAX]}
    return json.dumps(action)


def to_wire_json(kind: str, action_json: str) -> str:
    """The reverse of `to_action_json`: an accepted action written the way the model writes
    answers, so a past answer can be shown back to it as one of its own turns."""
    data = json.loads(action_json)
    beliefs = [
        {"player": player, "suspicion": b["suspicion"], "reason": b.get("reason", "")}
        for player, b in data.get("beliefs", {}).items()
    ]
    wire: _Wire
    if kind == "wolf_chat":
        wire = WireChat(text=data["text"], note=data.get("note", ""))
    elif kind == "night_target":
        wire = WireTarget(target=data["target"] or "", note=data.get("note", ""))
    elif kind == "bid":
        wire = WireBid(
            bid=data["bid"],
            message=data.get("message", ""),
            intent=data.get("intent") or "none",
            target=data.get("target") or "",
            note=data.get("note", ""),
            beliefs=[WireBelief(**b) for b in beliefs],
            cites=[WireCite(**c) for c in data.get("cites", [])],
        )
    elif kind == "vote":
        wire = WireVote(
            target=data["target"] or "",
            reason=data.get("reason", ""),
            note=data.get("note", ""),
            beliefs=[WireBelief(**b) for b in beliefs],
        )
    else:
        wire = WireMemory(summary=data["summary"])
    return wire.model_dump_json()
