"""Cost ledger: a hard spending cap per provider, saved to disk so it holds across runs.

Every paid model call reserves its estimated cost first, then settles with the real cost.
"""

import json
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from pathlib import Path

# The OpenAI cap was $4.50 until Oct 21, 2026, when the owner added $4.10 of credit for experiments.
# Total spent so far was about $3.4 then, so $7.25 keeps a margin whichever way the $4.10 is counted.
DEFAULT_CAPS: dict[str, Decimal] = {
    "openai": Decimal("7.25"),
    "anthropic": Decimal("4.50"),
    "groq": Decimal("0"),
    "cerebras": Decimal("0"),
}


LOCK_WAIT_S = 10.0  # how long to wait for another process to finish writing the file
LOCK_STALE_S = 10.0  # a lock this old was left behind by a crashed process


def _is_stale(lock: Path) -> bool:
    """A lock left behind by a process that died. One that is gone, or being removed right now,
    is not stale: the caller simply looks again."""
    try:
        return time.time() - lock.stat().st_mtime > LOCK_STALE_S
    except OSError:
        return False


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
    # Reservations live in memory per Ledger, so separate processes share only settled spend (one
    # process cannot see another's in-flight calls). The file itself is locked, so no process
    # loses another's settled spend or trips on its temporary file.
    def __init__(self, path: Path, caps: Mapping[str, Decimal] | None = None) -> None:
        self._path = path
        self._caps = dict(DEFAULT_CAPS if caps is None else caps)
        self._open: dict[int, Reservation] = {}
        self._ids = count(1)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """One process at a time reads or writes the file (a plain lock file, no new library)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_suffix(".lock")
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except (FileExistsError, PermissionError):  # Windows: PermissionError while deleted
                if _is_stale(lock):
                    lock.unlink(missing_ok=True)
                    continue
                if time.monotonic() > deadline:
                    raise LedgerError(f"ledger file {self._path} is locked by another process")
                time.sleep(0.01)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def _load(self) -> dict[str, Decimal]:
        with self._locked():
            return self._read()

    def _read(self) -> dict[str, Decimal]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {key: Decimal(value) for key, value in data["spent"].items()}
        except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as exc:
            raise LedgerError(f"cannot read ledger file {self._path}") from exc

    def _save(self, spent: dict[str, Decimal]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(f".{os.getpid()}.tmp")
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
        with self._locked():
            spent = self._read()
            spent[reservation.key] = spent.get(reservation.key, Decimal("0")) + actual
            self._save(spent)

    def release(self, reservation: Reservation) -> None:
        """Give the reservation back after a call that failed and cost nothing."""
        self._close(reservation)
