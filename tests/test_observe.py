"""Langfuse is attached only when its three variables are set, through LiteLLM's callback."""

import sys
from decimal import Decimal
from pathlib import Path

import litellm
import pytest

from werewolf.llm.transport import LANGFUSE_VARS, attach_langfuse
from werewolf.runtime import build_client

ALL = {
    "LANGFUSE_PUBLIC_KEY": "pk-test",
    "LANGFUSE_SECRET_KEY": "sk-test",
    "LANGFUSE_HOST": "https://cloud.langfuse.test",
}


@pytest.fixture(autouse=True)
def clean_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(litellm, "callbacks", [])
    for name in LANGFUSE_VARS:
        monkeypatch.delenv(name, raising=False)


def test_with_nothing_set_nothing_is_attached_and_nothing_is_imported() -> None:
    assert attach_langfuse({}) is False
    assert litellm.callbacks == []
    assert not any("langfuse" in name for name in sys.modules if name.startswith("opentelemetry"))


@pytest.mark.parametrize("missing", LANGFUSE_VARS)
def test_with_any_one_of_the_three_missing_it_stays_off(missing: str) -> None:
    env = {name: value for name, value in ALL.items() if name != missing}
    assert attach_langfuse(env) is False
    assert litellm.callbacks == []


def test_a_blank_value_counts_as_missing() -> None:
    assert attach_langfuse({**ALL, "LANGFUSE_SECRET_KEY": ""}) is False


def test_with_all_three_set_every_call_is_sent_through_the_otel_callback() -> None:
    assert attach_langfuse(ALL) is True
    assert litellm.callbacks == ["langfuse_otel"]


def test_attaching_twice_does_not_send_every_call_twice() -> None:
    attach_langfuse(ALL)
    attach_langfuse(ALL)
    assert litellm.callbacks == ["langfuse_otel"]


def test_the_packages_the_callback_needs_are_installed() -> None:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider

    assert OTLPSpanExporter and TracerProvider


def test_a_run_started_with_the_variables_set_attaches_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    build_client("gpt-4o-mini", Decimal("0.10"), root=tmp_path)
    assert litellm.callbacks == []  # no variables: no Langfuse
    for name, value in ALL.items():
        monkeypatch.setenv(name, value)
    build_client("gpt-4o-mini", Decimal("0.10"), root=tmp_path)
    assert litellm.callbacks == ["langfuse_otel"]
