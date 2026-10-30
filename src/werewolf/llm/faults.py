"""Fault switches: ways to make the model misbehave, so the failure paths of a game are proven
and not assumed. They exist only when `APP_ENV=test`; in any other process a `FAULTS` setting
changes nothing and is warned about. Nothing here is set in the Docker image or the compose file.

  timeout     every call fails as if the provider never answered
  bad_json    every answer is broken JSON (the engine asks once more, then uses its default)
  never_ends  every answer is valid and does nothing (no kill, no vote, no talk), so the game can
              only end at the round limit
  retry_burn  every answer is broken JSON and costs money, so retries only stop at the run budget
"""

import json
import logging
import os
from collections.abc import Collection, Mapping
from decimal import Decimal
from typing import Any

from werewolf.llm.client import Transport
from werewolf.llm.types import Completion, Request

log = logging.getLogger(__name__)
FAULTS = ("timeout", "bad_json", "never_ends", "retry_burn")
BROKEN = "this is {not json"
BURN_COST = Decimal("0.05")  # what one wasted answer costs under retry_burn


def _names(env: Mapping[str, str]) -> list[str]:
    return [name.strip() for name in env.get("FAULTS", "").split(",") if name.strip()]


def active_faults(env: Mapping[str, str] | None = None) -> list[str]:
    """The switches that are really on: none unless this is a test process."""
    env = os.environ if env is None else env
    return _names(env) if env.get("APP_ENV") == "test" else []


def with_faults(transport: Transport, env: Mapping[str, str] | None = None) -> Transport:
    """The transport itself, unless this is a test process with switches set."""
    env = os.environ if env is None else env
    wanted = _names(env)
    if not wanted:
        return transport
    if env.get("APP_ENV") != "test":
        log.warning("FAULTS is set but APP_ENV is not 'test', so no fault is applied")
        return transport
    for name in wanted:
        if name not in FAULTS:
            raise ValueError(f"unknown fault '{name}'; use one of: {', '.join(FAULTS)}")
    return FaultyTransport(transport, wanted)


def quiet_answer(schema: Mapping[str, Any] | None) -> str:
    """A valid answer that does nothing: no text, no target, a zero bid, no beliefs."""
    properties: Mapping[str, Mapping[str, Any]] = (schema or {}).get("properties", {})

    def empty(spec: Mapping[str, Any]) -> Any:
        if "enum" in spec:
            return "none" if "none" in spec["enum"] else spec["enum"][0]
        return {"integer": 0, "number": 0.0, "array": [], "boolean": False}.get(
            str(spec.get("type")), ""
        )

    return json.dumps({name: empty(spec) for name, spec in properties.items()})


class FaultyTransport:
    """Stands in front of a real transport and never reaches it for a switched call."""

    def __init__(self, inner: Transport, faults: Collection[str]) -> None:
        self._inner = inner
        self._faults = list(faults)

    def provider(self, model: str) -> str:
        return self._inner.provider(model)

    def estimate(self, request: Request) -> Decimal:
        return self._inner.estimate(request)

    def _reply(self, request: Request, text: str, cost: Decimal = Decimal("0")) -> Completion:
        return Completion(
            model=request.model, text=text, prompt_tokens=10, completion_tokens=5, cost=cost
        )

    async def call(self, request: Request) -> Completion:
        for fault in self._faults:  # the first switch in the list that applies wins
            if fault == "timeout":
                raise TimeoutError("fault: the provider did not answer in time")
            if fault == "bad_json":
                return self._reply(request, BROKEN)
            if fault == "retry_burn":
                return self._reply(request, BROKEN, BURN_COST)
            if fault == "never_ends":
                return self._reply(request, quiet_answer(request.schema_))
        return await self._inner.call(request)
