"""Play mode runs one game for a visitor who has picked the cards.

The visitor chooses one strategy card for each of wolves, villagers, the Seer and the Doctor (or
the default instructions for a role). Nothing else comes from them: not the model, not the seed,
not the rules. `check_picks` turns the four choices into cards or refuses them in plain words;
`play_visitor_game` plays the game on the v3 rules and says whether it finished or had to stop.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from werewolf.agents.llm_agent import LLMAgent
from werewolf.agents.scripted import policy
from werewolf.engine.actions import Agent, FatalAgentError
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings
from werewolf.llm.client import LLMClient
from werewolf.strategies.cards import CARDS_DIR, assign_cards, load_card

# the four things a visitor chooses, and the role each one is for
SIDES: dict[str, Role] = {
    "wolf": Role.WEREWOLF,
    "villager": Role.VILLAGER,
    "seer": Role.SEER,
    "doctor": Role.DOCTOR,
}
DEFAULT = "default"
WOLF_CHAT_MESSAGES = 5
# More than this share of answers falling back to a default means the model was not really
# playing (a provider out of credit, say): the game is kept out of the list of real games.
BROKEN_SHARE = 0.25


class PickError(ValueError):
    """A card choice that cannot be played, worded for the visitor."""


@dataclass
class VisitorGame:
    status: Literal["finished", "stopped"]
    log: GameLog | None
    cost: Decimal
    reason: str | None = None


def check_picks(picks: Mapping[str, str], directory: Path = CARDS_DIR) -> dict[Role, str]:
    """The cards to play by role, from the visitor's four choices. "default" leaves a role on the
    default instructions. A card must exist and be a card for that role; a version, if given, must
    be the card's current one."""
    unknown = sorted(set(picks) - set(SIDES))
    if unknown:
        raise PickError(f"unknown choice: {', '.join(unknown)}")
    missing = [side for side in SIDES if side not in picks]
    if missing:
        raise PickError(f"choose a card, or default, for: {', '.join(missing)}")
    chosen: dict[Role, str] = {}
    for side, role in SIDES.items():
        pick = picks[side]
        if pick == DEFAULT:
            continue
        try:
            card = load_card(pick, directory)
        except ValueError as exc:
            raise PickError(f"{side}: {exc}") from exc
        if card.role is not role:
            raise PickError(f"{card.id} is a {card.role.value} card, not a {role.value} card")
        if "@" in pick and pick != card.ref:
            raise PickError(f"{pick} is out of date; the current version is {card.ref}")
        chosen[role] = card.ref
    return chosen


def _agents(
    seed: int,
    settings: Settings,
    model: str,
    client: LLMClient | None,
    run_id: str,
    max_tokens: int,
) -> dict[str, Agent]:
    players = new_game(seed, settings).players
    if client is None:  # the free scripted players: they never talk, but the cards are logged
        wolves = [p.name for p in players if p.role is Role.WEREWOLF]
        return {p.name: policy(wolves) for p in players}
    return {
        p.name: LLMAgent(
            p.name,
            client,
            model,
            cache_salt=run_id,
            game_id=run_id,
            summarize=settings.summarize_rounds,
            card=load_card(settings.cards[p.name]).prompt_text if p.name in settings.cards else "",
            max_tokens=max_tokens,
        )
        for p in players
    }


async def play_visitor_game(
    picks: Mapping[str, str],
    seed: int,
    *,
    model: str = "gpt-4.1-mini",
    client: LLMClient | None = None,
    agents: Mapping[str, Agent] | None = None,
    max_tokens: int = 300,
    directory: Path = CARDS_DIR,
) -> VisitorGame:
    """Play one game with the visitor's cards on the v3 rules.

    `client=None` plays free scripted players (the fake model). The client's own spending limit is
    the per-game budget: when it is reached the game stops and nothing is kept. A game whose
    answers mostly fell back to defaults is returned as stopped, with its log, so it can be
    stored but never shown as a real game.
    """
    by_role = check_picks(picks, directory)
    settings = Settings(wolf_chat_messages=WOLF_CHAT_MESSAGES, summarize_rounds=client is not None)
    try:
        cards = assign_cards(
            {p.name: p.role for p in new_game(seed, settings).players}, by_role, {}, directory
        )
    except ValueError as exc:
        raise PickError(str(exc)) from exc
    settings = settings.model_copy(update={"cards": cards})
    run_id = uuid.uuid4().hex[:12]
    players = agents or _agents(seed, settings, model, client, run_id, max_tokens)
    try:
        state = await play_game(seed, settings, players)
    except FatalAgentError as exc:
        return VisitorGame("stopped", None, Decimal("0"), reason=str(exc))
    log = to_log(state, run_id=run_id, model=model if client is not None else "")
    failed = sum(1 for call in log.calls if call.failed)
    if log.calls and failed / len(log.calls) > BROKEN_SHARE:
        return VisitorGame(
            "stopped",
            log,
            log.stats.cost,
            reason=f"{failed} of {len(log.calls)} answers failed, so this was not a real game "
            "(is the model provider out of credit?)",
        )
    return VisitorGame("finished", log, log.stats.cost)
