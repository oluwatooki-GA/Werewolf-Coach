import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from werewolf.llm.ledger import DEFAULT_CAPS, Ledger, LedgerBlocked, LedgerError

D = Decimal


def make(tmp_path: Path, **caps: str) -> Ledger:
    return Ledger(tmp_path / "ledger.json", {k: D(v) for k, v in caps.items()} or None)


def test_default_caps_are_4_50_for_paid_providers_and_zero_for_free_tiers() -> None:
    assert DEFAULT_CAPS == {
        "openai": D("7.25"),
        "anthropic": D("4.50"),
        "groq": D("0"),
        "cerebras": D("0"),
    }


def test_reserve_within_the_cap_is_allowed(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    ledger.reserve("openai", D("0.40"))
    assert ledger.remaining("openai") == D("0.60")


def test_reserving_exactly_the_cap_is_allowed(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="4.50")
    ledger.reserve("openai", D("4.50"))
    assert ledger.remaining("openai") == D("0")


def test_one_cent_over_the_cap_is_blocked(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="4.50")
    with pytest.raises(LedgerBlocked):
        ledger.reserve("openai", D("4.51"))


def test_spending_up_to_the_cap_then_one_more_cent_is_blocked(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="4.50")
    ledger.settle(ledger.reserve("openai", D("4.50")), D("4.50"))
    with pytest.raises(LedgerBlocked):
        ledger.reserve("openai", D("0.01"))


def test_a_free_tier_blocks_any_cost_but_allows_zero(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.reserve("groq", D("0"))
    with pytest.raises(LedgerBlocked):
        ledger.reserve("groq", D("0.001"))


def test_an_unknown_provider_fails_closed(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.json")
    with pytest.raises(LedgerBlocked):
        ledger.reserve("mistral", D("0"))


def test_reserved_but_unsettled_money_counts_against_the_cap(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    ledger.reserve("openai", D("0.70"))
    with pytest.raises(LedgerBlocked):
        ledger.reserve("openai", D("0.40"))


def test_release_returns_the_reserved_money_after_a_failed_call(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    reservation = ledger.reserve("openai", D("0.70"))
    ledger.release(reservation)
    ledger.reserve("openai", D("1.00"))


def test_settle_records_the_actual_cost_and_frees_the_difference(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    ledger.settle(ledger.reserve("openai", D("0.50")), D("0.20"))
    assert ledger.spent("openai") == D("0.20")
    assert ledger.remaining("openai") == D("0.80")


def test_an_actual_cost_above_the_estimate_is_recorded_truthfully(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    ledger.settle(ledger.reserve("openai", D("0.50")), D("1.20"))
    assert ledger.spent("openai") == D("1.20")
    with pytest.raises(LedgerBlocked):
        ledger.reserve("openai", D("0.01"))


def test_a_reservation_cannot_be_settled_or_released_twice(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    reservation = ledger.reserve("openai", D("0.50"))
    ledger.settle(reservation, D("0.50"))
    with pytest.raises(LedgerError):
        ledger.settle(reservation, D("0.50"))
    with pytest.raises(LedgerError):
        ledger.release(reservation)


def test_spend_persists_across_ledgers_on_the_same_file(tmp_path: Path) -> None:
    first = make(tmp_path, openai="1.00")
    first.settle(first.reserve("openai", D("0.60")), D("0.60"))
    second = make(tmp_path, openai="1.00")
    assert second.spent("openai") == D("0.60")
    with pytest.raises(LedgerBlocked):
        second.reserve("openai", D("0.50"))


def test_a_missing_file_starts_at_zero(tmp_path: Path) -> None:
    assert make(tmp_path, openai="1.00").spent("openai") == D("0")


def test_a_corrupt_file_fails_closed_instead_of_resetting_to_zero(tmp_path: Path) -> None:
    (tmp_path / "ledger.json").write_text("{not json")
    ledger = make(tmp_path, openai="1.00")
    with pytest.raises(LedgerError):
        ledger.reserve("openai", D("0.01"))


def test_the_file_stores_amounts_as_exact_decimal_strings(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    ledger.settle(ledger.reserve("openai", D("0.10")), D("0.10"))
    ledger.settle(ledger.reserve("openai", D("0.20")), D("0.20"))
    saved = json.loads((tmp_path / "ledger.json").read_text())
    assert saved["spent"]["openai"] == "0.30"


def test_floats_and_negative_amounts_are_rejected(tmp_path: Path) -> None:
    ledger = make(tmp_path, openai="1.00")
    a_float: Any = 0.1
    with pytest.raises(TypeError):
        ledger.reserve("openai", a_float)
    with pytest.raises(ValueError):
        ledger.reserve("openai", D("-0.10"))
    reservation = ledger.reserve("openai", D("0.10"))
    with pytest.raises(ValueError):
        ledger.settle(reservation, D("-0.01"))
