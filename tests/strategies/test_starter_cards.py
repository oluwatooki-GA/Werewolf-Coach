"""The 12 real cards in cards/: they load, pass every check, and differ from each other."""

from collections import Counter
from pathlib import Path

from werewolf.agents.prompt import build_messages, estimate_tokens
from werewolf.engine.actions import BidTask
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.views import make_view
from werewolf.strategies.cards import check_card, load_all

CARDS = Path(__file__).resolve().parents[2] / "cards"


def test_all_twelve_cards_load_and_pass_every_check() -> None:
    cards = load_all(CARDS)
    assert len(cards) == 12
    assert all(check_card(card) == [] for card in cards.values())


def test_each_role_has_three_cards() -> None:
    counts = Counter(card.role for card in load_all(CARDS).values())
    assert counts == {Role.WEREWOLF: 3, Role.VILLAGER: 3, Role.SEER: 3, Role.DOCTOR: 3}


def test_cards_of_one_role_expect_different_moves() -> None:
    cards = load_all(CARDS).values()
    for role in Role:
        moves = [tuple(sorted(c.expected_moves)) for c in cards if c.role is role]
        assert len(set(moves)) == len(moves), role


def test_a_card_keeps_the_first_prompt_under_three_thousand_tokens() -> None:
    state = new_game(1)
    for card in load_all(CARDS).values():
        player = next(p.name for p in state.players if p.role is card.role)
        messages = build_messages(
            make_view(state, player), BidTask(max_bid=3, max_chars=300), card=card.prompt_text
        )
        assert estimate_tokens(messages) < 3000, card.id
        assert card.prompt_text in messages[0]["content"]
