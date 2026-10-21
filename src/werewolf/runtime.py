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


# Requests per minute allowed by a free key. Cerebras reports 5 (and 150 an hour) in its
# response headers; a paid provider is left unpaced unless asked.
DEFAULT_RPM = {"cerebras": 5}


def default_max_tokens(model: str, message_chars: int = 300) -> int:
    """Output budget per answer. Claude models write longer answers (notes, belief reasons), and
    at 300 tokens a bid answer was cut off before its belief table. Longer messages (about 3
    characters a token) get that much extra room."""
    base = 1000 if model.split("/")[-1].startswith("claude") else 300
    return base + max(0, message_chars - 300) // 3


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
    model: str,
    max_spend: Decimal | None,
    root: Path = Path("."),
    max_concurrency: int = 8,
    requests_per_minute: int | None = None,
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
    pace = dict(DEFAULT_RPM)
    if requests_per_minute is not None:
        pace[provider] = requests_per_minute
    return LLMClient(
        transport,
        Ledger(root / "data" / "ledger.json"),
        FileCache(root / "data" / "cache" / "llm"),
        max_concurrency=max_concurrency,
        run_budget=max_spend,
        requests_per_minute={p: n for p, n in pace.items() if p == provider},
    )
