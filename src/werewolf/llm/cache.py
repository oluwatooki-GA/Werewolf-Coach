"""Response cache: one JSON file per request, so a repeated prompt costs nothing."""

import hashlib
import json
import os
import uuid
from pathlib import Path

from pydantic import ValidationError

from werewolf.llm.types import Completion, Request


def cache_key(request: Request) -> str:
    """Everything that changes the answer. The routing hint does not, so it is left out."""
    identity = {
        "model": request.model,
        "messages": request.messages,
        "schema": request.schema_,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "salt": request.cache_salt,
    }
    text = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FileCache:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def get(self, key: str) -> Completion | None:
        try:
            return Completion.model_validate_json((self._dir / f"{key}.json").read_text("utf-8"))
        except (OSError, ValueError, ValidationError):  # missing, unreadable or the wrong shape
            return None

    def put(self, key: str, completion: Completion) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        temp = (
            self._dir / f".{key}.{uuid.uuid4().hex}.tmp"
        )  # unique, so parallel writes never clash
        temp.write_text(completion.model_dump_json(), encoding="utf-8")
        os.replace(temp, self._dir / f"{key}.json")
