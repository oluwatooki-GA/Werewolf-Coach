"""Play mode runs one game with the cards a visitor picked, on the v3 rules, with no network."""

import asyncio

import pytest

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import Agent, FatalAgentError, Task
from werewolf.engine.log import replays_exactly
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.views import PlayerView
from werewolf.play.service import PickError, check_picks, play_visitor_game
from werewolf.store.games import rule_version

PICKS = {
    "wolf": "wolf.lie_low",
    "villager": "villager.track_votes",
    "seer": "seer.reveal_now",
    "doctor": "doctor.protect_seer",
}


def play(picks: dict[str, str] = PICKS, seed: int = 3, **options: object):  # type: ignore[no-untyped-def]
    return asyncio.run(play_visitor_game(picks, seed, **options))  # type: ignore[arg-type]


def roles(seed: int) -> dict[str, Role]:
    return {p.name: p.role for p in new_game(seed).players}


def test_four_cards_play_a_finished_game_with_those_cards() -> None:
    game = play()
    assert game.status == "finished" and game.log is not None and game.reason is None
    played = game.log.settings.cards
    for seat, ref in played.items():
        role = roles(3)[seat]
        assert (
            ref.split(".")[0]
            == {
                Role.WEREWOLF: "wolf",
                Role.VILLAGER: "villager",
                Role.SEER: "seer",
                Role.DOCTOR: "doctor",
            }[role]
        )
    assert set(played) == set(roles(3))  # every seat has the card for its role


def test_the_game_is_played_on_the_v3_rules_and_replays_exactly() -> None:
    game = play()
    assert game.log is not None
    assert rule_version(game.log) == "v3"
    assert game.log.settings.wolf_chat_messages == 5
    assert replays_exactly(game.log)


def test_default_leaves_a_role_on_the_default_instructions() -> None:
    game = play({**PICKS, "wolf": "default", "seer": "default"})
    assert game.log is not None
    by_role = {roles(3)[seat]: ref for seat, ref in game.log.settings.cards.items()}
    assert Role.WEREWOLF not in by_role and Role.SEER not in by_role
    assert by_role[Role.VILLAGER] == "villager.track_votes@2"


def test_all_default_is_a_game_with_no_cards() -> None:
    game = play(dict.fromkeys(PICKS, "default"))
    assert game.log is not None and game.log.settings.cards == {}


def test_a_card_for_the_wrong_role_is_refused_before_anything_is_played() -> None:
    with pytest.raises(PickError, match="Villager card, not a Werewolf card"):
        play({**PICKS, "wolf": "villager.track_votes"})


def test_an_unknown_card_is_refused() -> None:
    with pytest.raises(PickError, match="no card 'wolf.nonsense'"):
        play({**PICKS, "wolf": "wolf.nonsense"})


def test_a_missing_choice_is_refused_and_named() -> None:
    with pytest.raises(PickError, match="choose a card, or default, for: seer, doctor"):
        check_picks({"wolf": "default", "villager": "default"})


def test_an_extra_choice_is_refused() -> None:
    with pytest.raises(PickError, match="unknown choice: model"):
        check_picks({**PICKS, "model": "claude-opus"})


def test_a_version_must_be_the_current_one() -> None:
    assert check_picks({**PICKS, "wolf": "wolf.lie_low@1"})[Role.WEREWOLF] == "wolf.lie_low@1"
    with pytest.raises(PickError, match="out of date"):
        check_picks({**PICKS, "wolf": "wolf.lie_low@9"})


class Stopping:
    """An agent whose first question hits the spending limit."""

    async def act(self, view: PlayerView, task: Task) -> object:
        raise FatalAgentError("the run budget is used up")


def test_a_game_that_hits_its_budget_stops_and_keeps_nothing() -> None:
    names = [p.name for p in new_game(3).players]
    agents: dict[str, Agent] = {n: Stopping() for n in names}
    game = play(agents=agents)
    assert game.status == "stopped" and game.log is None
    assert game.reason == "the run budget is used up"


def test_a_game_whose_answers_mostly_failed_is_stopped_not_shown_as_real() -> None:
    names = [p.name for p in new_game(3).players]

    def garbage(view: PlayerView, task: Task) -> object:
        return "this is not json"

    agents: dict[str, Agent] = {n: ScriptedAgent(garbage) for n in names}
    game = play(agents=agents)
    assert game.status == "stopped"
    assert game.log is not None  # kept, so it can be stored out of sight
    assert game.reason is not None and "was not a real game" in game.reason
