"""Anthropic only caches a prompt prefix that ends at a cache_control marker; OpenAI needs none."""

import asyncio
from decimal import Decimal
from typing import Any

import litellm
import pytest
from litellm import ModelResponse

from werewolf.llm.transport import CACHE_WRITE_MULTIPLIER, LiteLLMTransport
from werewolf.llm.types import Request

D = Decimal
SYSTEM, USER = "s" * 300, "u" * 300


def reply(prompt: int, completion: int, read: int, written: int) -> ModelResponse:
    details = {"cached_tokens": read, "cache_creation_tokens": written}
    return ModelResponse(
        model="m",
        choices=[
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"a":"x"}'},
            }
        ],
        usage={
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "prompt_tokens_details": details,
        },
    )


class Capture:
    def __init__(self, response: ModelResponse) -> None:
        self.response, self.kwargs = response, {}

    async def __call__(self, **kwargs: Any) -> ModelResponse:
        self.kwargs = kwargs
        return self.response


def call(
    model: str, response: ModelResponse, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, Capture]:
    capture = Capture(response)
    monkeypatch.setattr(litellm, "acompletion", capture)
    request = Request.model_validate(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER},
            ],
            "max_tokens": 300,
        }
    )
    return asyncio.run(LiteLLMTransport().call(request)), capture


def test_a_claude_call_marks_the_system_message_as_cacheable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = call("claude-haiku-5-5", reply(1000, 100, 0, 0), monkeypatch)[1].kwargs["messages"]
    assert sent[0] == {
        "role": "system",
        "content": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
    }
    assert sent[1] == {"role": "user", "content": USER}  # only the fixed part is marked


def test_an_openai_call_is_sent_as_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = call("gpt-4.1-nano", reply(1000, 100, 0, 0), monkeypatch)[1].kwargs["messages"]
    assert sent[0] == {"role": "system", "content": SYSTEM}


def test_a_cache_write_is_billed_at_the_premium_and_a_read_at_the_discount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert CACHE_WRITE_MULTIPLIER == D("1.25")  # Anthropic's price for a 5-minute entry
    done, _ = call("claude-haiku-5-5", reply(2000, 100, 600, 1000), monkeypatch)
    # 400 fresh + 600 read + 1000 written (at 1.25x) input tokens, and 100 output tokens
    fresh, read = D(400) * D("1e-07"), D(600) * D("1e-08")
    written, out = D(1000) * D("1.25e-07"), D(100) * D("5e-07")
    assert done.cost == fresh + read + written + out and done.cached_tokens == 600
