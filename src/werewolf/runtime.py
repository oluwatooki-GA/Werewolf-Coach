"""Wiring for real runs: read .env, check keys, and build the model client."""

import os
from decimal import Decimal
from pathlib import Path

from werewolf.llm.cache import FileCache
from werewolf.llm.client import LLMClient
from werewolf.llm.ledger import Ledger
from werewolf.llm.transport import FREE_PROVIDERS, LiteLLMTransport

KEY_FOR = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "groq": "GROQ_API_KEY",
}


def load_env(path: Path) -> list[str]:
    """Put KEY=VALUE lines from a .env file into the environment, keeping any value already
    set. Returns the names that were read; values are never returned or printed."""
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip("'\"")
        os.environ.setdefault(name, value)
        names.append(name)
    return names


def build_client(
    model: str, max_spend: Decimal | None, root: Path = Path("."), max_concurrency: int = 8
) -> LLMClient:
    """A client for real calls. A paid model needs an explicit spending limit for this run."""
    transport = LiteLLMTransport()
    provider = transport.provider(model)
    if provider not in FREE_PROVIDERS and max_spend is None:
        raise RuntimeError(f"{model} is a paid model: give a spending limit with --max-spend")
    load_env(root / ".env")
    key = KEY_FOR.get(provider)
    if key is not None and not os.environ.get(key):
        raise RuntimeError(f"{key} is not set (add it to .env)")
    return LLMClient(
        transport,
        Ledger(root / "data" / "ledger.json"),
        FileCache(root / "data" / "cache" / "llm"),
        max_concurrency=max_concurrency,
        run_budget=max_spend,
    )
