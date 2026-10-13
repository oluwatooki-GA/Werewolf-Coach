"""Cost ledger: a hard spending cap per provider, saved to disk so it holds across runs.

Every paid model call reserves its estimated cost first, then settles with the real cost.
"""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from pathlib import Path

DEFAULT_CAPS: dict[str, Decimal] = {
    "openai": Decimal("4.50"),
    "anthropic": Decimal("4.50"),
    "groq": Decimal("0"),
    "cerebras": Decimal("0"),
}


class LedgerBlocked(Exception):
    """The call would pass the cap, or the provider is unknown."""


class LedgerError(Exception):
    """The ledger file is unreadable or a reservation was misused."""


@dataclass(frozen=True)
class Reservation:
    id: int
    key: str
    amount: Decimal


def _check_amount(amount: Decimal) -> None:
    if not isinstance(amount, Decimal):
        raise TypeError("amounts must be Decimal, not float")
    if amount < 0:
        raise ValueError("amounts cannot be negative")


class Ledger:
    # ponytail: reservations live in memory per Ledger; separate processes share only settled
    # spend. Fine for one machine running games in one process; add file locking if that changes.
    def __init__(self, path: Path, caps: Mapping[str, Decimal] | None = None) -> None:
        self._path = path
        self._caps = dict(DEFAULT_CAPS if caps is None else caps)
        self._open: dict[int, Reservation] = {}
        self._ids = count(1)

    def _load(self) -> dict[str, Decimal]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {key: Decimal(value) for key, value in data["spent"].items()}
        except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as exc:
            raise LedgerError(f"cannot read ledger file {self._path}") from exc

    def _save(self, spent: dict[str, Decimal]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        body = json.dumps({"spent": {k: str(v) for k, v in spent.items()}}, sort_keys=True)
        temp.write_text(body, encoding="utf-8")
        os.replace(temp, self._path)

    def _cap(self, key: str) -> Decimal:
        if key not in self._caps:
            raise LedgerBlocked(f"unknown provider '{key}'")
        return self._caps[key]

    def _reserved(self, key: str) -> Decimal:
        return sum((r.amount for r in self._open.values() if r.key == key), Decimal("0"))

    def spent(self, key: str) -> Decimal:
        return self._load().get(key, Decimal("0"))

    def remaining(self, key: str) -> Decimal:
        return self._cap(key) - self.spent(key) - self._reserved(key)

    def reserve(self, key: str, estimate: Decimal) -> Reservation:
        _check_amount(estimate)
        if estimate > self.remaining(key):
            raise LedgerBlocked(f"{key}: ${estimate} would pass the ${self._cap(key)} cap")
        reservation = Reservation(next(self._ids), key, estimate)
        self._open[reservation.id] = reservation
        return reservation

    def _close(self, reservation: Reservation) -> None:
        if self._open.pop(reservation.id, None) is None:
            raise LedgerError("reservation was already settled or released")

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        """Record the real cost, even if it is above the estimate or the cap."""
        _check_amount(actual)
        self._close(reservation)
        spent = self._load()
        spent[reservation.key] = spent.get(reservation.key, Decimal("0")) + actual
        self._save(spent)

    def release(self, reservation: Reservation) -> None:
        """Give the reservation back after a call that failed and cost nothing."""
        self._close(reservation)
