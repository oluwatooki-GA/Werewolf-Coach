"""What one model call used: tokens, money, time. Logged next to the answer it produced."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int = 0  # prompt tokens served from the provider's prompt cache
    cost: Decimal = Decimal("0")  # dollars; 0 for a response-cache hit or a free tier
    latency_s: float = 0.0
    cache_hit: bool = False  # answered from our own response cache, no model call
    truncated: bool = False  # the model stopped because it hit the output limit
