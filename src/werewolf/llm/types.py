from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from werewolf.llm.ledger import LedgerBlocked


class UnknownPrice(LedgerBlocked):
    """The model has no known price, so its cost cannot be limited. Refused."""


class Request(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    model: str
    messages: list[dict[str, str]]
    schema_: dict[str, Any] | None = Field(
        default=None, alias="schema"
    )  # JSON schema for the answer
    temperature: float = 0.7
    max_tokens: int = 300
    cache_salt: str = ""  # same prompt + different salt = a fresh answer, not a cache hit
    prompt_cache_key: str | None = None  # routing hint for the provider's prompt cache only


class Completion(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int = 0
    cost: Decimal = Decimal("0")
    latency_s: float = 0.0
    cache_hit: bool = False
    truncated: bool = False
