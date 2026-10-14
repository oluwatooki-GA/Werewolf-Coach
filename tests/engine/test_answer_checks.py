"""The rules the engine applies to a bid and to a vote before it accepts them."""

import pytest

from werewolf.engine.actions import Action, BidAction, ChatAction, VoteAction
from werewolf.engine.day import bid_check
from werewolf.engine.vote import vote_check

ALIVE = ["Ada", "Bo", "Cy"]


def bid(**fields: object) -> BidAction:
    return BidAction.model_validate({"bid": 1, "message": "hi", **fields})


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (ChatAction(text="hi"), "expected a bid"),
        (bid(bid=4), "you can bid at most 3"),
        (bid(message="x" * 301), "at most 300 characters"),
        (bid(message="   "), "needs a message"),
        (bid(target="Ada"), "another living player"),  # oneself
        (bid(target="Zed"), "another living player"),  # not at the table
    ],
)
def test_a_bid_that_breaks_a_rule_is_turned_down_with_the_reason(
    action: Action, reason: str
) -> None:
    check = bid_check("Ada", max_bid=3, limit=300, alive=ALIVE)
    assert reason in (check(action) or "")


def test_a_good_bid_a_silent_bid_and_a_targeted_bid_are_accepted() -> None:
    check = bid_check("Ada", max_bid=3, limit=300, alive=ALIVE)
    assert check(bid(bid=3, message="x" * 300)) is None
    assert check(BidAction(bid=0)) is None
    assert check(bid(target="Bo", intent="ask")) is None


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (ChatAction(text="hi"), "expected a vote"),
        (VoteAction(target="Zed"), "vote for one of: Bo, Cy"),
        (VoteAction(target="Bo", reason="x" * 301), "at most 300 characters"),
    ],
)
def test_a_vote_that_breaks_a_rule_is_turned_down_with_the_reason(
    action: Action, reason: str
) -> None:
    check = vote_check(("Bo", "Cy"), limit=300)
    assert reason in (check(action) or "")


def test_a_vote_for_a_player_and_an_abstention_are_accepted() -> None:
    check = vote_check(("Bo", "Cy"), limit=300)
    assert check(VoteAction(target="Bo", reason="dodged")) is None
    assert check(VoteAction(target=None)) is None
