"""Prices for models the bundled LiteLLM price list does not have.

Each entry is copied from the provider's own pricing page, with its source and the date it was
checked. (input, output, cached input) in dollars per token. A model that is in neither this
table nor the bundled list has no known price, and a call to it is refused.
"""

from decimal import Decimal

EXTRA_PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    # Claude Haiku 5.5, for prompts up to 100,000 tokens: $0.10 in, $0.50 out, $0.01 cache hit
    # per million tokens. Ours are about 2,000, far below. (Over 100,000 tokens the page lists
    # $0.50 and $2.50.) Source: platform.claude.com/docs/en/about-claude/pricing, 2026-10-14.
    "claude-haiku-5-5": (Decimal("1e-07"), Decimal("5e-07"), Decimal("1e-08")),
    # Claude Sonnet 5.5: $2 in, $10 out, $0.10 cache hit (0.05x base) per million tokens.
    # Source: platform.claude.com/docs/en/about-claude/pricing, 2026-10-21.
    "claude-sonnet-5-5": (Decimal("2e-06"), Decimal("1e-05"), Decimal("1e-07")),
}
