"""The real transport: LiteLLM. This is the only file that imports `litellm`."""

import json
import time
from decimal import Decimal
from typing import Any

import litellm
from litellm.exceptions import RateLimitError

from werewolf.llm.prices import EXTRA_PRICES
from werewolf.llm.types import Completion, RateLimited, Request, UnknownPrice

FREE_PROVIDERS = frozenset({"groq", "cerebras"})  # free tiers: cost 0, limited by rate limits
_ACCEPTS_CACHE_KEY = frozenset({"openai", "groq"})  # providers that take prompt_cache_key
# Claude 5 models reject the temperature setting ("`temperature` is deprecated for this model").
_NO_TEMPERATURE = ("claude-haiku-5", "claude-sonnet-5", "claude-opus-5")


class LiteLLMTransport:
    def __init__(self, timeout: float = 60.0, retries: int = 2) -> None:
        self._timeout = timeout
        self._retries = retries

    def provider(self, model: str) -> str:
        try:
            return str(litellm.get_llm_provider(model)[1])
        except Exception as exc:  # LiteLLM raises its own error types for names it cannot place
            raise UnknownPrice(f"no price for model '{model}': provider not recognised") from exc

    def _prices(self, model: str) -> tuple[Decimal, Decimal, Decimal]:
        entry = litellm.model_cost.get(model)
        if entry is None or not entry.get("input_cost_per_token"):
            bare = model.split("/")[-1]  # "anthropic/claude-haiku-5-5" -> "claude-haiku-5-5"
            if bare in EXTRA_PRICES:
                return EXTRA_PRICES[bare]
            raise UnknownPrice(f"no price for model '{model}' in LiteLLM's list or our own table")
        price_in = Decimal(str(entry["input_cost_per_token"]))
        price_out = Decimal(str(entry["output_cost_per_token"]))
        cached = entry.get("cache_read_input_token_cost")
        return price_in, price_out, Decimal(str(cached)) if cached else price_in

    def estimate(self, request: Request) -> Decimal:
        """Worst case: a generous guess at the prompt, and the full output limit used."""
        if self.provider(request.model) in FREE_PROVIDERS:
            return Decimal("0")
        price_in, price_out, _ = self._prices(request.model)
        chars = sum(len(m["content"]) for m in request.messages)
        if request.schema_ is not None:
            chars += len(json.dumps(request.schema_))
        return (chars // 3 + 1) * price_in + request.max_tokens * price_out

    async def call(self, request: Request) -> Completion:
        provider = self.provider(request.model)
        free = provider in FREE_PROVIDERS
        prices = None if free else self._prices(request.model)

        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "timeout": self._timeout,
            "num_retries": self._retries,
        }
        if not request.model.split("/")[-1].startswith(_NO_TEMPERATURE):
            kwargs["temperature"] = request.temperature
        if request.schema_ is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": request.schema_, "strict": True},
            }
        if request.prompt_cache_key and provider in _ACCEPTS_CACHE_KEY:
            kwargs["prompt_cache_key"] = request.prompt_cache_key
        if "gpt-oss" in request.model:  # reasoning tokens count against max_tokens: keep them few
            kwargs["reasoning_effort"] = "low"

        started = time.perf_counter()
        try:
            response = await litellm.acompletion(**kwargs)
        except RateLimitError as exc:  # still limited after LiteLLM's own retries
            raise RateLimited(f"{provider} rate limit reached: {exc}") from exc
        latency = time.perf_counter() - started
        assert isinstance(response, litellm.ModelResponse)

        choice = response.choices[0]
        usage = response.usage
        prompt = int(usage.prompt_tokens)
        completion = int(usage.completion_tokens)
        details = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        cost = Decimal("0")
        if prices is not None:
            price_in, price_out, price_cached = prices
            cost = (prompt - cached) * price_in + cached * price_cached + completion * price_out
        return Completion(
            model=request.model,
            text=choice.message.content or "",
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            cost=cost,
            latency_s=latency,
            # Claude reports a cut-off tool answer as a plain "stop", so also count an answer
            # that used the whole output budget as cut off.
            truncated=choice.finish_reason == "length" or completion >= request.max_tokens,
        )
