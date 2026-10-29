import asyncio
from decimal import Decimal
from typing import Any

import litellm
import pytest
from litellm import ModelResponse

from werewolf.llm.prices import EXTRA_PRICES
from werewolf.llm.transport import FREE_PROVIDERS, LiteLLMTransport
from werewolf.llm.types import RateLimited, Request, UnknownPrice

D = Decimal
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def request(model: str = "gpt-4.1-nano", **kw: object) -> Request:
    base: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "s" * 300},
            {"role": "user", "content": "u" * 300},
        ],
        "schema": SCHEMA,
        "max_tokens": 300,
    }
    return Request.model_validate({**base, **kw})


def response(
    content: str = '{"a":"x"}',
    finish: str = "stop",
    prompt: int = 1200,
    completion: int = 300,
    cached: int | None = 1024,
) -> ModelResponse:
    usage: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if cached is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached}
    return ModelResponse(
        model="gpt-4.1-nano",
        choices=[
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content},
            }
        ],
        usage=usage,
    )


class Capture:
    """Stands in for litellm.acompletion: records the call, returns a prepared response."""

    def __init__(self, reply: ModelResponse) -> None:
        self.reply, self.kwargs = reply, {}

    async def __call__(self, **kwargs: Any) -> ModelResponse:
        self.kwargs = kwargs
        return self.reply


def call(model: str, reply: ModelResponse, **kw: object) -> tuple[Any, Capture]:
    capture = Capture(reply)
    litellm.acompletion = capture  # restored by the fixture below
    done = asyncio.run(LiteLLMTransport().call(request(model, **kw)))
    return done, capture


@pytest.fixture(autouse=True)
def restore_litellm() -> Any:
    original = litellm.acompletion
    yield
    litellm.acompletion = original


def test_the_player_model_has_a_price() -> None:
    entry = litellm.model_cost["gpt-4.1-nano"]
    assert entry["input_cost_per_token"] > 0 and entry["output_cost_per_token"] > 0


def test_a_model_the_price_list_lacks_is_refused_not_guessed() -> None:
    # A model that is in neither the bundled list nor our own price table has no known cost.
    with pytest.raises(UnknownPrice):
        LiteLLMTransport().estimate(request("claude-imaginary-9"))


def test_nano_is_priced_as_planned() -> None:
    entry = litellm.model_cost["gpt-4.1-nano"]
    assert (entry["input_cost_per_token"], entry["output_cost_per_token"]) == (1e-07, 4e-07)
    assert entry["cache_read_input_token_cost"] == 2.5e-08


def test_the_provider_names_match_the_ledger_keys() -> None:
    t = LiteLLMTransport()
    assert t.provider("gpt-4.1-nano") == "openai"
    assert t.provider("claude-haiku-5-5") == "anthropic"
    assert t.provider("cerebras/gpt-oss-120b") == "cerebras"
    assert t.provider("groq/openai/gpt-oss-120b") == "groq"
    assert FREE_PROVIDERS == {"groq", "cerebras"}


def test_tokens_cached_tokens_and_cost_come_back_exactly() -> None:
    done, _ = call("gpt-4.1-nano", response(), max_tokens=500)
    assert (done.prompt_tokens, done.completion_tokens, done.cached_tokens) == (1200, 300, 1024)
    # 176 fresh input + 1024 cached + 300 output tokens, priced per token
    assert done.cost == D("176") * D("1e-07") + D("1024") * D("2.5e-08") + D("300") * D("4e-07")
    assert done.cost == D("0.0001632")
    assert done.text == '{"a":"x"}' and not done.truncated and not done.cache_hit


def test_our_cost_agrees_with_litellms_own() -> None:
    reply = response()
    done, _ = call("gpt-4.1-nano", reply)
    assert abs(float(done.cost) - litellm.completion_cost(completion_response=reply)) < 1e-12


def test_a_response_without_cached_token_details_counts_none_cached() -> None:
    done, _ = call("gpt-4.1-nano", response(cached=None, prompt=1000, completion=100))
    assert done.cached_tokens == 0
    assert done.cost == D("1000") * D("1e-07") + D("100") * D("4e-07")


def test_a_cut_off_answer_is_flagged() -> None:
    done, _ = call("gpt-4.1-nano", response(finish="length"))
    assert done.truncated


def test_an_empty_answer_comes_back_as_empty_text() -> None:
    done, _ = call("gpt-4.1-nano", response(content=""))
    assert done.text == ""


def test_free_tier_providers_cost_nothing_even_though_the_price_map_has_a_price() -> None:
    assert litellm.model_cost["cerebras/gpt-oss-120b"]["input_cost_per_token"] > 0
    done, _ = call("cerebras/gpt-oss-120b", response(cached=None))
    assert done.cost == D("0")
    assert LiteLLMTransport().estimate(request("cerebras/gpt-oss-120b")) == D("0")


def test_an_unknown_paid_model_fails_closed() -> None:
    with pytest.raises(UnknownPrice, match="no price"):
        LiteLLMTransport().estimate(request("gpt-9-imaginary"))
    with pytest.raises(UnknownPrice):
        call("gpt-9-imaginary", response())


def test_the_estimate_is_a_worst_case_above_the_real_cost() -> None:
    done, _ = call("gpt-4.1-nano", response(prompt=200, completion=60, cached=0))
    assert LiteLLMTransport().estimate(request()) > done.cost
    # with the output limit at 300 tokens the hold-back is about 300 * $0.0000004 plus the prompt
    assert LiteLLMTransport().estimate(request()) < D("0.001")


def test_a_smaller_output_limit_holds_back_less_money() -> None:
    t = LiteLLMTransport()
    assert t.estimate(request(max_tokens=300)) < t.estimate(request(max_tokens=600))


def test_the_answer_is_requested_as_strict_json_with_our_schema_and_limits() -> None:
    _, capture = call("gpt-4.1-nano", response(), temperature=0.4)
    k = capture.kwargs
    assert k["model"] == "gpt-4.1-nano" and k["max_tokens"] == 300 and k["temperature"] == 0.4
    assert k["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "answer", "schema": SCHEMA, "strict": True},
    }
    assert k["timeout"] > 0


def test_without_a_schema_no_response_format_is_sent() -> None:
    _, capture = call("gpt-4.1-nano", response(), schema=None)
    assert "response_format" not in capture.kwargs


def test_the_prompt_cache_key_is_sent_only_where_the_provider_accepts_it() -> None:
    _, openai = call("gpt-4.1-nano", response(), prompt_cache_key="game:Ada")
    assert openai.kwargs["prompt_cache_key"] == "game:Ada"
    _, cerebras = call("cerebras/gpt-oss-120b", response(), prompt_cache_key="game:Ada")
    assert "prompt_cache_key" not in cerebras.kwargs
    _, nokey = call("gpt-4.1-nano", response())
    assert "prompt_cache_key" not in nokey.kwargs


def test_reasoning_models_are_asked_to_think_briefly_so_they_do_not_eat_the_output_limit() -> None:
    _, capture = call("cerebras/gpt-oss-120b", response())
    assert capture.kwargs["reasoning_effort"] == "low"
    _, plain = call("gpt-4.1-nano", response())
    assert "reasoning_effort" not in plain.kwargs


def test_latency_is_measured() -> None:
    done, _ = call("gpt-4.1-nano", response())
    assert done.latency_s >= 0


def test_a_rate_limit_error_becomes_a_hard_stop_with_a_clear_message() -> None:
    async def refuse(**kwargs: Any) -> ModelResponse:
        raise litellm.RateLimitError(
            message="Requests per minute limit exceeded",
            llm_provider="cerebras",
            model="gpt-oss-120b",
        )

    litellm.acompletion = refuse
    with pytest.raises(RateLimited, match="cerebras rate limit"):
        asyncio.run(LiteLLMTransport().call(request("cerebras/gpt-oss-120b")))


def test_a_refused_key_becomes_a_hard_stop_not_a_bad_answer() -> None:
    async def refuse(**kwargs: Any) -> ModelResponse:
        raise litellm.AuthenticationError(
            message="invalid x-api-key", llm_provider="anthropic", model="claude-haiku-5-5"
        )

    litellm.acompletion = refuse
    with pytest.raises(RateLimited, match="anthropic refused the call"):
        asyncio.run(LiteLLMTransport().call(request("claude-haiku-5-5")))


def test_openai_reporting_an_expired_key_as_a_bad_request_is_still_a_hard_stop() -> None:
    async def expired(**kwargs: Any) -> ModelResponse:
        raise litellm.BadRequestError(
            message="OpenAIException - Your API key has expired. Create a new API key to continue.",
            llm_provider="openai",
            model="gpt-4.1-nano",
        )

    litellm.acompletion = expired
    with pytest.raises(RateLimited, match="openai refused the call.*API key has expired"):
        asyncio.run(LiteLLMTransport().call(request("gpt-4.1-nano")))


def test_an_ordinary_bad_request_is_not_mistaken_for_a_bad_key() -> None:
    async def too_long(**kwargs: Any) -> ModelResponse:
        raise litellm.BadRequestError(
            message="maximum context length is exceeded",
            llm_provider="openai",
            model="gpt-4.1-nano",
        )

    litellm.acompletion = too_long
    with pytest.raises(litellm.BadRequestError):  # stays an ordinary failed answer
        asyncio.run(LiteLLMTransport().call(request("gpt-4.1-nano")))


def test_a_retired_model_is_a_hard_stop_that_names_the_model() -> None:
    async def gone(**kwargs: Any) -> ModelResponse:
        raise litellm.NotFoundError(
            message="OpenAIException - The model `gpt-4.1-nano` has been deprecated",
            llm_provider="openai",
            model="gpt-4.1-nano",
        )

    litellm.acompletion = gone
    with pytest.raises(RateLimited, match="openai has no model gpt-4.1-nano.*deprecated"):
        asyncio.run(LiteLLMTransport().call(request("gpt-4.1-nano")))


# --- Claude: priced from Anthropic's own pricing page --------------------------------------


def test_claude_haiku_5_5_is_priced_from_our_table_because_the_bundled_list_lacks_it() -> None:
    assert "claude-haiku-5-5" not in litellm.model_cost  # why the table exists
    assert EXTRA_PRICES["claude-haiku-5-5"] == (
        D("1e-07"),
        D("5e-07"),
        D("1e-08"),
    )  # $0.10 / $0.50 per M
    done, _ = call("claude-haiku-5-5", response(prompt=1000, completion=100, cached=None))
    assert done.cost == D("1000") * D("1e-07") + D("100") * D("5e-07") == D("0.00015")


def test_the_price_works_with_or_without_the_provider_prefix() -> None:
    t = LiteLLMTransport()
    assert t.estimate(request("claude-haiku-5-5")) == t.estimate(
        request("anthropic/claude-haiku-5-5")
    )
    assert t.provider("claude-haiku-5-5") == "anthropic"


def test_a_haiku_call_is_cheap_to_hold_back() -> None:
    assert LiteLLMTransport().estimate(request("claude-haiku-5-5")) < D("0.001")


def test_sonnet_5_5_in_the_bundled_list_agrees_with_anthropics_page() -> None:
    entry = litellm.model_cost["claude-sonnet-5-5"]
    assert (entry["input_cost_per_token"], entry["output_cost_per_token"]) == (2e-06, 1e-05)


def test_the_bundled_list_wins_when_it_has_the_model() -> None:
    done, _ = call("gpt-4.1-nano", response(prompt=1000, completion=100, cached=None))
    assert done.cost == D("1000") * D("1e-07") + D("100") * D("4e-07")  # not from our table


def test_claude_5_models_are_not_sent_a_temperature_because_they_refuse_one() -> None:
    for model in ("claude-haiku-5-5", "anthropic/claude-haiku-5-5", "claude-sonnet-5-5"):
        _, capture = call(model, response(), temperature=0.7)
        assert "temperature" not in capture.kwargs, model


def test_other_models_still_get_their_temperature() -> None:
    for model in ("gpt-4.1-nano", "cerebras/gpt-oss-120b"):
        _, capture = call(model, response(), temperature=0.4)
        assert capture.kwargs["temperature"] == 0.4, model


def test_an_answer_that_used_its_whole_output_budget_counts_as_cut_off() -> None:
    # Claude reports a cut-off tool answer as an ordinary "stop"; the token count gives it away.
    done, _ = call("claude-haiku-5-5", response(finish="stop", completion=300, cached=None))
    assert done.truncated
    fine, _ = call("claude-haiku-5-5", response(finish="stop", completion=299, cached=None))
    assert not fine.truncated


def test_a_larger_output_budget_is_respected_when_judging_a_cut_off() -> None:
    done, _ = call(
        "claude-haiku-5-5", response(finish="stop", completion=300, cached=None), max_tokens=500
    )
    assert not done.truncated


def test_claude_sonnet_5_5_is_priced_from_our_table() -> None:
    assert EXTRA_PRICES["claude-sonnet-5-5"] == (D("2e-06"), D("1e-05"), D("1e-07"))
    done, _ = call("claude-sonnet-5-5", response(prompt=1000, completion=100, cached=None))
    assert done.cost == D("0.003")  # 1,000 in at $2 and 100 out at $10 per million
