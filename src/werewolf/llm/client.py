"""The one door for model calls: cache first, then the ledger, then the model."""

import asyncio
from decimal import Decimal
from typing import Protocol

from werewolf.llm.cache import FileCache, cache_key
from werewolf.llm.ledger import Ledger, LedgerBlocked
from werewolf.llm.types import Completion, Request


class Transport(Protocol):
    def provider(self, model: str) -> str: ...

    def estimate(self, request: Request) -> Decimal:
        """Worst-case cost in dollars. Raises UnknownPrice for a model with no known price."""
        ...

    async def call(self, request: Request) -> Completion: ...


class LLMClient:
    def __init__(
        self,
        transport: Transport,
        ledger: Ledger,
        cache: FileCache,
        *,
        max_concurrency: int = 8,
        run_budget: Decimal | None = None,
    ) -> None:
        self._transport = transport
        self._ledger = ledger
        self._cache = cache
        self._max_concurrency = max_concurrency
        self._run_budget = run_budget
        self._run_spent = Decimal("0")
        self._run_reserved = Decimal("0")
        self._limits: dict[tuple[int, str], asyncio.Semaphore] = {}

    def _limit(self, provider: str) -> asyncio.Semaphore:
        key = (id(asyncio.get_running_loop()), provider)  # one limit per provider per event loop
        if key not in self._limits:
            self._limits[key] = asyncio.Semaphore(self._max_concurrency)
        return self._limits[key]

    async def complete(self, request: Request) -> Completion:
        key = cache_key(request)
        hit = self._cache.get(key)
        if hit is not None:
            return hit.model_copy(
                update={"cost": Decimal("0"), "latency_s": 0.0, "cache_hit": True}
            )

        provider = self._transport.provider(request.model)
        estimate = self._transport.estimate(request)
        if self._run_budget is not None:
            if self._run_spent + self._run_reserved + estimate > self._run_budget:
                raise LedgerBlocked(f"run budget ${self._run_budget} would be passed")
        reservation = self._ledger.reserve(provider, estimate)
        self._run_reserved += estimate
        try:
            async with self._limit(provider):
                completion = await self._transport.call(request)
        except BaseException:
            self._ledger.release(reservation)
            self._run_reserved -= estimate
            raise
        self._ledger.settle(reservation, completion.cost)
        self._run_reserved -= estimate
        self._run_spent += completion.cost
        if not completion.truncated:  # a cut-off answer is never reused
            self._cache.put(key, completion)
        return completion
