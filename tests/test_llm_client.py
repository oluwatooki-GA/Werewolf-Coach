import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import Ledger, LedgerBlocked
from werewolf.llm.types import Completion, Request, UnknownPrice

D = Decimal
FREE = {"groq", "cerebras"}
PRICES = {  # dollars per token: (input, output)
    "gpt-4.1-nano": (D("0.0000001"), D("0.0000004")),
    "groq/gpt-oss": (D("0.0000002"), D("0.0000008")),
    "cerebras/gpt-oss": (D("0.0000002"), D("0.0000008")),
    "anthropic/claude": (D("0.000001"), D("0.000005")),
}


class FakeTransport:
    def __init__(self, text: str = "hi", delay: float = 0.0) -> None:
        self.calls: list[Request] = []
        self.active = self.peak = 0
        self.text, self.delay = text, delay
        self.fail: Exception | None = None
        self.truncate = False
        self.during_call: list[Decimal] = []
        self.ledger: Ledger | None = None
        self.actual_scale = D("1")

    def provider(self, model: str) -> str:
        return model.split("/")[0] if "/" in model else "openai"

    def _price(self, model: str) -> tuple[Decimal, Decimal]:
        if model not in PRICES:
            raise UnknownPrice(f"no price for model '{model}'")
        return (D("0"), D("0")) if self.provider(model) in FREE else PRICES[model]

    def _prompt_tokens(self, request: Request) -> int:
        return sum(len(m["content"]) for m in request.messages) // 4 + 1

    def estimate(self, request: Request) -> Decimal:
        price_in, price_out = self._price(request.model)
        return self._prompt_tokens(request) * price_in + request.max_tokens * price_out

    async def call(self, request: Request) -> Completion:
        self.calls.append(request)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.ledger is not None:
                self.during_call.append(self.ledger.remaining(self.provider(request.model)))
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail:
                raise self.fail
            price_in, price_out = self._price(request.model)
            prompt, out = self._prompt_tokens(request), 20
            return Completion(
                model=request.model,
                text=self.text,
                prompt_tokens=prompt,
                completion_tokens=out,
                cached_tokens=0,
                cost=(prompt * price_in + out * price_out) * self.actual_scale,
                latency_s=0.5,
                truncated=self.truncate,
            )
        finally:
            self.active -= 1


def request(content: str = "hello", **kw: object) -> Request:
    base: dict[str, object] = {
        "model": "gpt-4.1-nano",
        "messages": [{"role": "user", "content": content}],
        "schema": None,
        "temperature": 0.7,
        "max_tokens": 300,
    }
    return Request.model_validate({**base, **kw})


class Setup:
    def __init__(
        self,
        tmp_path: Path,
        caps: dict[str, Decimal] | None = None,
        max_concurrency: int = 8,
        run_budget: Decimal | None = None,
    ) -> None:
        default = {"openai": D("4.50"), "anthropic": D("4.50"), "groq": D("0"), "cerebras": D("0")}
        self.transport = FakeTransport()
        self.ledger = Ledger(tmp_path / "ledger.json", caps if caps is not None else default)
        self.cache = FileCache(tmp_path / "cache")
        self.client = LLMClient(
            self.transport,
            self.ledger,
            self.cache,
            max_concurrency=max_concurrency,
            run_budget=run_budget,
        )
        self.transport.ledger = self.ledger

    def run(self, *requests: Request) -> list[Completion]:
        async def go() -> list[Completion]:
            return list(await asyncio.gather(*(self.client.complete(r) for r in requests)))

        return asyncio.run(go())


def test_a_miss_reserves_the_worst_case_calls_the_model_and_settles_the_real_cost(
    tmp_path: Path,
) -> None:
    s = Setup(tmp_path)
    (done,) = s.run(request())
    estimate = s.transport.estimate(request())
    assert s.transport.during_call == [D("4.50") - estimate]  # money held back during the call
    assert s.ledger.spent("openai") == done.cost < estimate  # then only the real cost is spent
    assert s.ledger.remaining("openai") == D("4.50") - done.cost
    assert not done.cache_hit and done.text == "hi"


def test_a_repeat_is_a_free_cache_hit_that_never_touches_the_ledger(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    (first,) = s.run(request())
    spent = s.ledger.spent("openai")
    (second,) = s.run(request())
    assert len(s.transport.calls) == 1
    assert second.cache_hit and second.cost == D("0") and second.latency_s == 0
    assert second.text == first.text and second.prompt_tokens == first.prompt_tokens
    assert s.ledger.spent("openai") == spent


def test_the_same_prompt_with_a_different_salt_asks_the_model_again_and_pays_again(
    tmp_path: Path,
) -> None:
    s = Setup(tmp_path)
    s.run(request(cache_salt="run-1"))
    s.run(request(cache_salt="run-2"))
    assert len(s.transport.calls) == 2
    one_call = s.transport.estimate(request())
    assert s.ledger.spent("openai") > 0 and s.ledger.spent("openai") < 2 * one_call
    s.run(request(cache_salt="run-2"))
    assert len(s.transport.calls) == 2  # same salt: free


def test_a_call_that_would_pass_the_cap_is_refused_before_any_model_call(tmp_path: Path) -> None:
    s = Setup(tmp_path, caps={"openai": D("0.00001")})
    with pytest.raises(LedgerBlocked):
        s.run(request())
    assert s.transport.calls == []
    assert s.ledger.spent("openai") == 0 and s.ledger.remaining("openai") == D("0.00001")


def test_a_failed_call_gives_the_money_back_and_caches_nothing(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.transport.fail = RuntimeError("rate limited")
    with pytest.raises(RuntimeError):
        s.run(request())
    assert s.ledger.remaining("openai") == D("4.50")
    s.transport.fail = None
    s.run(request())
    assert len(s.transport.calls) == 2  # nothing was cached by the failure


def test_a_truncated_answer_is_returned_but_not_cached(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.transport.truncate = True
    (done,) = s.run(request())
    assert done.truncated
    s.run(request())
    assert len(s.transport.calls) == 2


def test_an_unknown_model_price_fails_closed(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    with pytest.raises(UnknownPrice, match="no price for model 'mystery'"):
        s.run(request(model="mystery"))
    assert s.transport.calls == []
    assert isinstance(UnknownPrice("x"), LedgerBlocked)  # so it is a hard stop for agents too


def test_free_tier_calls_cost_nothing_and_pass_a_zero_cap(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    (done,) = s.run(request(model="cerebras/gpt-oss"))
    assert done.cost == D("0")
    assert s.ledger.spent("cerebras") == 0


def test_a_paid_provider_with_a_zero_cap_is_blocked(tmp_path: Path) -> None:
    s = Setup(tmp_path, caps={"openai": D("0")})
    with pytest.raises(LedgerBlocked):
        s.run(request())


def test_a_real_cost_above_the_estimate_is_still_recorded(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.transport.actual_scale = D("1000")
    (done,) = s.run(request())
    assert s.ledger.spent("openai") == done.cost > s.transport.estimate(request())


def test_the_concurrency_limit_holds(tmp_path: Path) -> None:
    s = Setup(tmp_path, max_concurrency=2)
    s.transport.delay = 0.03
    s.run(*(request(f"prompt {i}") for i in range(6)))
    assert len(s.transport.calls) == 6
    assert s.transport.peak == 2


def test_the_limit_is_per_provider(tmp_path: Path) -> None:
    s = Setup(tmp_path, max_concurrency=1)
    s.transport.delay = 0.05
    s.run(request("a"), request("b", model="cerebras/gpt-oss"))
    assert s.transport.peak == 2  # one call to each provider ran side by side


def test_the_run_budget_refuses_a_call_that_would_pass_it(tmp_path: Path) -> None:
    probe = Setup(tmp_path / "probe")
    one = probe.transport.estimate(request())
    s = Setup(tmp_path / "real", run_budget=one * 2)
    s.transport.delay = 0.02  # so the three calls below overlap and hold money at once
    s.run(request("one"))
    with pytest.raises(LedgerBlocked, match="run budget"):
        s.run(request("two"), request("three"), request("four"))
    assert s.ledger.spent("openai") < one * 2  # nothing past the budget was spent


def test_a_cache_hit_does_not_use_the_run_budget(tmp_path: Path) -> None:
    probe = Setup(tmp_path / "probe")
    one = probe.transport.estimate(request())
    s = Setup(tmp_path / "real", run_budget=one)
    s.run(request())
    for _ in range(5):
        s.run(request())  # all hits
    assert len(s.transport.calls) == 1


def test_a_failed_call_gives_the_run_budget_back(tmp_path: Path) -> None:
    probe = Setup(tmp_path / "probe")
    one = probe.transport.estimate(request())
    s = Setup(tmp_path / "real", run_budget=one)
    s.transport.fail = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        s.run(request())
    s.transport.fail = None
    s.run(request())  # the budget is whole again


def test_the_run_budget_counts_all_providers_together(tmp_path: Path) -> None:
    probe = Setup(tmp_path / "probe")
    (first,) = probe.run(request())
    claude_call = probe.transport.estimate(request(model="anthropic/claude"))
    s = Setup(tmp_path / "real", run_budget=first.cost + claude_call - D("0.000000001"))
    s.run(request())  # openai: fits, and spends first.cost
    with pytest.raises(LedgerBlocked, match="run budget"):
        s.run(request(model="anthropic/claude"))  # fits its own cap, but not the run budget
