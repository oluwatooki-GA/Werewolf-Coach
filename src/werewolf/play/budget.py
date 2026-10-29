"""The play caps: may another game start, given what has been spent?

Money is counted in the database (the `play_spend` table), not in the ledger file, because a
deployed server's disk is not kept. A game may start only if both caps can pay for one more game at
the estimated price, after setting aside the same estimate for every game already being played.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import Connection

from werewolf.store.play import spent_today, spent_total

State = Literal["open", "paused", "busy"]


@dataclass(frozen=True)
class Caps:
    daily: Decimal  # dollars a day, all visitors together
    total: Decimal  # dollars in all
    estimate: Decimal  # what one game is assumed to cost, to leave room for it


@dataclass(frozen=True)
class Verdict:
    state: State  # open: start one; paused: no money left; busy: wait for a running game
    reason: str
    games_left: int = 0  # more games the caps can pay for, after the ones running now


def check(conn: Connection, caps: Caps, *, running: int, day: str) -> Verdict:
    """The verdict for starting one more game now. `running` is how many are being played."""
    left_today = caps.daily - Decimal(str(spent_today(conn, day)))
    left_in_all = caps.total - Decimal(str(spent_total(conn)))
    if left_today < caps.estimate:
        return Verdict("paused", "Today's play budget is used up. Play opens again tomorrow.")
    if left_in_all < caps.estimate:
        return Verdict("paused", "The total play budget is used up, so play mode is closed.")
    room = min(left_today, left_in_all) - caps.estimate * running
    left = max(0, int(room / caps.estimate))
    if room < caps.estimate:
        return Verdict("busy", "Games are being played right now. Try again in a minute.", left)
    return Verdict("open", "", left)
