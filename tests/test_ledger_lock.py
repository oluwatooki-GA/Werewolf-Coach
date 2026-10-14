"""Several processes can share one ledger file without losing spend or crashing."""

import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from werewolf.llm.ledger import LOCK_STALE_S, Ledger, LedgerError

D = Decimal

WORKER = """
import sys
from decimal import Decimal
from pathlib import Path
from werewolf.llm.ledger import Ledger

ledger = Ledger(Path(sys.argv[1]))
for _ in range(int(sys.argv[2])):
    ledger.settle(ledger.reserve("openai", Decimal("0.01")), Decimal("0.01"))
"""


def test_processes_settling_at_the_same_time_lose_nothing(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    workers = [
        subprocess.Popen([sys.executable, "-c", WORKER, str(path), "40"], cwd=Path.cwd())
        for _ in range(4)
    ]
    assert [w.wait(timeout=120) for w in workers] == [0, 0, 0, 0]
    assert Ledger(path).spent("openai") == D("1.60")  # 4 processes x 40 settles x $0.01
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ledger.json"]  # no temp or lock left


def test_a_lock_left_by_a_crashed_process_is_cleared(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    lock = path.with_suffix(".lock")
    lock.write_text("")
    old = time.time() - 2 * LOCK_STALE_S
    os.utime(lock, (old, old))
    ledger = Ledger(path)
    ledger.settle(ledger.reserve("openai", D("0.05")), D("0.05"))
    assert ledger.spent("openai") == D("0.05") and not lock.exists()


def test_a_lock_that_stays_held_stops_the_run_instead_of_hanging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import werewolf.llm.ledger as module

    monkeypatch.setattr(module, "LOCK_WAIT_S", 0.2)
    path = tmp_path / "ledger.json"
    path.with_suffix(".lock").write_text("")  # fresh, so not stale: someone is working
    with pytest.raises(LedgerError):
        Ledger(path).spent("openai")
