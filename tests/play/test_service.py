"""Play mode runs one game with a card chosen for each player, on the v3 rules, with no network."""

import asyncio
from decimal import Decimal

import pytest

from werewolf.agents.scripted import ScriptedAgent, policy
from werewolf.engine.actions import Agent, FatalAgentError, Task
from werewolf.engine.log import replays_exactly
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.views import PlayerView
from werewolf.play.service import PickError, check_picks, play_visitor_game, seats
from werewolf.store.games import rule_version

SEED = 3
CARD = {
    Role.WEREWOLF: "wolf.lie_low",
    Role.VILLAGER: "villager.track_votes",
    Role.SEER: "seer.reveal_now",
    Role.DOCTOR: "doctor.protect_seer",
}


def roles(seed: int = SEED) -> dict[str, Role]:
    return {p.name: p.role for p in new_game(seed).players}


def seat_of(role: Role, n: int = 0) -> str:
    return [name for name, r in roles().items() if r is role][n]


def picks(**changes: str) -> dict[str, str]:
    """A card for every seat, by its role's usual card; `changes` set one seat's card by name."""
    chosen = {name: CARD[role] for name, role in roles().items()}
    return {**chosen, **changes}


def play(chosen: dict[str, str] | None = None, seed: int = SEED, **options: object):  # type: ignore[no-untyped-def]
    return asyncio.run(play_visitor_game(seed, chosen or picks(), **options))  # type: ignore[arg-type]


def table(seed: int = SEED) -> dict[str, Agent]:
    wolves = [p.name for p in new_game(seed).players if p.role is Role.WEREWOLF]
    return {p.name: policy(wolves) for p in new_game(seed).players}


def test_the_table_is_the_eight_seats_and_their_roles_for_a_seed() -> None:
    assert dict(seats(SEED)) == roles()
    assert len(seats(SEED)) == 8
    assert seats(SEED) != seats(SEED + 1)  # another seed deals another table


def test_every_player_gets_the_card_chosen_for_that_player() -> None:
    first, second = seat_of(Role.WEREWOLF, 0), seat_of(Role.WEREWOLF, 1)
    game = play(picks(**{first: "wolf.lie_low", second: "wolf.fake_seer"}))
    assert game.status == "finished" and game.log is not None and game.reason is None
    cards = game.log.settings.cards
    assert cards[first].startswith("wolf.lie_low@") and cards[second].startswith("wolf.fake_seer@")
    assert set(cards) == set(roles())  # all eight seats have a card


def test_the_four_villagers_can_each_play_a_different_card() -> None:
    villagers = [seat_of(Role.VILLAGER, n) for n in range(4)]
    wanted = [
        "villager.ask_questions",
        "villager.track_votes",
        "villager.quiet_observer",
        "default",
    ]
    game = play(picks(**dict(zip(villagers, wanted, strict=True))))
    assert game.log is not None
    cards = game.log.settings.cards
    assert [cards.get(v, "default").split("@")[0] for v in villagers] == wanted


def test_the_game_is_played_on_the_v3_rules_and_replays_exactly() -> None:
    game = play()
    assert game.log is not None
    assert rule_version(game.log) == "v3"
    assert game.log.settings.wolf_chat_messages == 5
    assert replays_exactly(game.log)


def test_default_leaves_a_player_on_the_default_instructions() -> None:
    wolf = seat_of(Role.WEREWOLF)
    game = play(picks(**{wolf: "default"}))
    assert game.log is not None
    assert wolf not in game.log.settings.cards
    assert seat_of(Role.WEREWOLF, 1) in game.log.settings.cards


def test_all_default_is_a_game_with_no_cards() -> None:
    game = play(dict.fromkeys(roles(), "default"))
    assert game.log is not None and game.log.settings.cards == {}


def test_a_card_for_the_wrong_role_is_refused_naming_the_player() -> None:
    villager = seat_of(Role.VILLAGER)
    with pytest.raises(PickError, match=rf"Werewolf card but {villager} is the Villager"):
        play(picks(**{villager: "wolf.lie_low"}))


def test_an_unknown_card_is_refused() -> None:
    with pytest.raises(PickError, match="no card 'wolf.nonsense'"):
        play(picks(**{seat_of(Role.WEREWOLF): "wolf.nonsense"}))


def test_a_player_left_out_is_refused_and_named() -> None:
    chosen = picks()
    gone = seat_of(Role.SEER)
    del chosen[gone]
    with pytest.raises(PickError, match=f"choose a card, or default, for: {gone}"):
        check_picks(SEED, chosen)


def test_a_seat_that_is_not_at_the_table_is_refused() -> None:
    with pytest.raises(PickError, match="no player named Zed"):
        check_picks(SEED, {**picks(), "Zed": "default"})


def test_a_version_must_be_the_current_one() -> None:
    wolf = seat_of(Role.WEREWOLF)
    assert check_picks(SEED, picks(**{wolf: "wolf.lie_low@1"}))[wolf] == "wolf.lie_low@1"
    with pytest.raises(PickError, match="out of date"):
        check_picks(SEED, picks(**{wolf: "wolf.lie_low@9"}))


class Stopping:
    """An agent whose first question hits the spending limit."""

    async def act(self, view: PlayerView, task: Task) -> object:
        raise FatalAgentError("the run budget is used up")


def test_a_game_that_hits_its_budget_stops_and_keeps_nothing() -> None:
    agents: dict[str, Agent] = {n: Stopping() for n in roles()}
    game = play(agents=agents)
    assert game.status == "stopped" and game.log is None
    assert game.reason == "the run budget is used up"


def test_a_game_whose_answers_mostly_failed_is_stopped_not_shown_as_real() -> None:
    def garbage(view: PlayerView, task: Task) -> object:
        return "this is not json"

    agents: dict[str, Agent] = {n: ScriptedAgent(garbage) for n in roles()}
    game = play(agents=agents)
    assert game.status == "stopped"
    assert game.log is not None  # kept, so it can be stored out of sight
    assert game.reason is not None and "was not a real game" in game.reason


class Spent:
    """Stands in for the model client: it only has to say what the run has paid for so far."""

    def __init__(self, dollars: str) -> None:
        self.run_spent = Decimal(dollars)


def test_a_game_stopped_by_its_budget_reports_what_it_had_spent() -> None:
    agents: dict[str, Agent] = {n: Stopping() for n in roles()}
    game = play(agents=agents, client=Spent("0.38"))
    assert game.status == "stopped" and game.cost == Decimal("0.38")


def test_a_finished_game_costs_at_least_what_the_client_paid() -> None:
    game = play(client=Spent("0.27"), agents=table())
    assert game.status == "finished" and game.cost == Decimal("0.27")


def test_free_scripted_games_cost_nothing() -> None:
    assert play().cost == Decimal("0")
