"""A slip guard for wolves: does a public message give away what the wolf chat said?

Small models forget which things the village may not know. Before a wolf's message is posted,
a cheap call compares it with the wolf's own wolf chat. A message that gives the chat away is sent
back once to be rewritten. This guard does not stop a wolf from lying or from naming its partner;
it only catches repeating the private plan.
"""

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf.llm.types import Request
from werewolf.prompts import load

REWRITE = load("leakguard")["rewrite"]

SYSTEM = load("leakguard")["system"]


class WireGuard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reveals: bool


def guard_schema() -> dict[str, Any]:
    schema = WireGuard.model_json_schema()
    schema["required"] = list(schema["properties"])
    return schema


def guard_request(
    model: str, secrets: Sequence[str], message: str, *, salt: str, max_tokens: int
) -> Request:
    chat = "\n".join(f"- {text}" for text in secrets)
    return Request(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": f"Private wolf chat:\n{chat}\n\nPublic message to check:\n{message}",
            },
        ],
        schema=guard_schema(),
        temperature=0.0,
        max_tokens=max_tokens,
        cache_salt=salt,
    )


def reveals(answer: str) -> bool:
    """The guard's verdict. An unreadable answer counts as no verdict, so as not revealing."""
    try:
        return WireGuard.model_validate(json.loads(answer)).reveals
    except (ValueError, ValidationError):
        return False
