"""The one door for model calls: cache first, then the ledger, then the model."""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
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
        requests_per_minute: Mapping[str, int] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._ledger = ledger
        self._cache = cache
        self._max_concurrency = max_concurrency
        self._run_budget = run_budget
        self._run_spent = Decimal("0")
        self._run_reserved = Decimal("0")
        self._limits: dict[tuple[int, str], asyncio.Semaphore] = {}
        self._rpm = dict(requests_per_minute or {})
        self._clock = clock
        self._sleep = sleep
        self._sent: dict[str, deque[float]] = {}  # when each provider's recent requests went out
        self._pacers: dict[tuple[int, str], asyncio.Lock] = {}

    @property
    def requests_per_minute(self) -> dict[str, int]:
        return dict(self._rpm)

    async def _pace(self, provider: str) -> None:
        """Wait until sending one more request keeps the provider under its per-minute limit."""
        limit = self._rpm.get(provider)
        if not limit:
            return
        key = (id(asyncio.get_running_loop()), provider)
        lock = self._pacers.setdefault(key, asyncio.Lock())
        async with lock:  # one at a time, so waiting calls go out in order
            window = self._sent.setdefault(provider, deque())
            while True:
                now = self._clock()
                while window and now - window[0] >= 60:
                    window.popleft()
                if len(window) < limit:
                    window.append(now)
                    return
                await self._sleep(60 - (now - window[0]))

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
            await self._pace(provider)
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
