import os
from decimal import Decimal
from pathlib import Path

import pytest

from werewolf.runtime import build_client, load_env


def test_load_env_reads_keys_without_overriding_existing_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "# a comment\n\nFIRST=one\nSECOND='two'\nTHIRD=\"three\"\nEXISTING=from-file\nnot a line\n"
    )
    monkeypatch.setattr(os, "environ", {"EXISTING": "from-shell"})  # a scratch environment
    names = load_env(tmp_path / ".env")

    assert (os.environ["FIRST"], os.environ["SECOND"], os.environ["THIRD"]) == (
        "one",
        "two",
        "three",
    )
    assert os.environ["EXISTING"] == "from-shell"
    assert names == ["FIRST", "SECOND", "THIRD", "EXISTING"]  # names only, never values


def test_load_env_with_no_file_does_nothing(tmp_path: Path) -> None:
    assert load_env(tmp_path / ".env") == []


def test_a_paid_model_without_a_spending_limit_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="--max-spend"):
        build_client("gpt-4.1-nano", max_spend=None, root=tmp_path)


def test_a_missing_key_is_reported_by_name_before_any_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_client("gpt-4.1-nano", max_spend=Decimal("0.10"), root=tmp_path)


def test_a_free_model_needs_no_spending_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    assert build_client("cerebras/gpt-oss-120b", max_spend=None, root=tmp_path) is not None


def test_the_error_never_contains_a_key_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-value")
    (tmp_path / ".env").write_text("OTHER=another-secret\n")
    with pytest.raises(RuntimeError) as caught:
        build_client("gpt-4.1-nano", max_spend=None, root=tmp_path)
    assert "secret" not in str(caught.value)
