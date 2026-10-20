"""An accusation has to point at a numbered line once there is one to point at."""

from test_day_tokens import bidders, cite, names, play_day, say, speeches

from werewolf.engine.actions import BidAction
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState


def rejections(state: GameState, player: str) -> list[list[str]]:
    return [c.errors for c in state.calls if c.player == player and c.rejected]


def test_a_first_accusation_needs_no_cite_because_there_is_nothing_to_cite() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    play_day(state, bidders(state, {a: [say(2, "b is odd", intent="accuse", target=b)]}))
    assert [s.text for s in speeches(state)][:1] == ["b is odd"]
    assert rejections(state, a) == []


def test_an_uncited_accusation_after_a_message_exists_is_rejected_then_asked_again() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    script = {
        a: [say(1, "hi")],
        b: [
            BidAction(bid=0),
            say(1, "a is odd", intent="accuse", target=a),  # no cite: rejected
            say(1, "a said hi and nothing else", intent="accuse", target=a, cites=[cite(a)]),
        ],
    }
    play_day(state, bidders(state, script))
    (errors,) = rejections(state, b)
    assert "must cite the numbered line" in errors[0]
    assert "a said hi and nothing else" in [s.text for s in speeches(state)]
    assert "a is odd" not in [s.text for s in speeches(state)]


def test_a_second_uncited_answer_falls_back_to_staying_quiet() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    script = {
        a: [say(1, "hi")],
        b: [
            BidAction(bid=0),
            say(1, "x", intent="accuse", target=a),
            say(1, "y", intent="accuse", target=a),
        ],
    }
    play_day(state, bidders(state, script))
    assert [s.text for s in speeches(state)] == ["hi"]
    assert any(c.failed for c in state.calls if c.player == b)


def test_other_intents_and_silent_bids_need_no_cite() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    script = {
        a: [say(1, "hi")],
        b: [BidAction(bid=0), say(1, "a, why?", intent="ask", target=a)],
    }
    play_day(state, bidders(state, script))
    assert "a, why?" in [s.text for s in speeches(state)]
    assert rejections(state, b) == []
    quiet = BidAction(bid=0, intent="accuse", target=a)  # nothing is posted, so nothing to cite
    state2 = new_game(seed=1)
    play_day(state2, bidders(state2, {a: [say(1, "hi")], b: [BidAction(bid=0), quiet]}))
    assert rejections(state2, b) == []
