"""Play mode runs one game for a visitor who has picked the cards.

The visitor sees the table (eight named seats, each with a role) and chooses a strategy card for
each player, or the default instructions. Nothing else comes from them: not the model, not the
rules. `check_picks` turns the choices into cards or refuses them in plain words;
`play_visitor_game` plays the game on the v3 rules and says whether it finished or had to stop.
"""

import uuid
from collections.abc import Callable, Mapping
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
from werewolf.engine.state import GameState, Settings
from werewolf.llm.client import LLMClient
from werewolf.strategies.cards import CARDS_DIR, load_card

DEFAULT = "default"
SEEDS = 1_000_000  # a table is dealt from a seed in 0..SEEDS-1
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


def seats(seed: int) -> list[tuple[str, Role]]:
    """The table a seed deals: each seat's name and role, in seat order."""
    return [(p.name, p.role) for p in new_game(seed).players]


def check_picks(seed: int, picks: Mapping[str, str], directory: Path = CARDS_DIR) -> dict[str, str]:
    """The card each seat plays, as 'id@version', from the visitor's choice for every player.
    "default" leaves a player on the default instructions (and out of the result). A card must
    exist and be a card for that seat's role; a version, if given, must be the current one."""
    table = dict(seats(seed))
    unknown = sorted(set(picks) - set(table))
    if unknown:
        raise PickError(f"no player named {', '.join(unknown)}")
    missing = [seat for seat in table if seat not in picks]
    if missing:
        raise PickError(f"choose a card, or default, for: {', '.join(missing)}")
    chosen: dict[str, str] = {}
    for seat, role in table.items():
        pick = picks[seat]
        if pick == DEFAULT:
            continue
        try:
            card = load_card(pick, directory)
        except ValueError as exc:
            raise PickError(f"{seat}: {exc}") from exc
        if card.role is not role:
            raise PickError(f"{card.id} is a {card.role.value} card but {seat} is the {role.value}")
        if "@" in pick and pick != card.ref:
            raise PickError(f"{pick} is out of date; the current version is {card.ref}")
        chosen[seat] = card.ref
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


def _spent(client: LLMClient | None) -> Decimal:
    return client.run_spent if client is not None else Decimal("0")


async def play_visitor_game(
    seed: int,
    picks: Mapping[str, str],
    *,
    model: str = "gpt-4.1-mini",
    client: LLMClient | None = None,
    agents: Mapping[str, Agent] | None = None,
    max_tokens: int = 300,
    directory: Path = CARDS_DIR,
    on_start: Callable[[GameState], None] | None = None,
) -> VisitorGame:
    """Play one game with the card the visitor chose for each player, on the v3 rules.

    `client=None` plays free scripted players (the fake model). The client's own spending limit is
    the per-game budget: when it is reached the game stops and nothing is kept. A game whose
    answers mostly fell back to defaults is returned as stopped, with its log, so it can be
    stored but never shown as a real game. `on_start` gets the game's state as soon as it is made,
    so the game can be read while it is played.
    """
    cards = check_picks(seed, picks, directory)
    settings = Settings(
        wolf_chat_messages=WOLF_CHAT_MESSAGES, summarize_rounds=client is not None, cards=cards
    )
    run_id = uuid.uuid4().hex[:12]
    players = agents or _agents(seed, settings, model, client, run_id, max_tokens)
    try:
        state = await play_game(seed, settings, players, on_start=on_start)
    except FatalAgentError as exc:
        return VisitorGame("stopped", None, _spent(client), reason=str(exc))
    log = to_log(state, run_id=run_id, model=model if client is not None else "")
    cost = max(log.stats.cost, _spent(client))  # the client's own count is the one money follows
    failed = sum(1 for call in log.calls if call.failed)
    if log.calls and failed / len(log.calls) > BROKEN_SHARE:
        return VisitorGame(
            "stopped",
            log,
            cost,
            reason=f"{failed} of {len(log.calls)} answers failed, so this was not a real game "
            "(is the model provider out of credit?)",
        )
    return VisitorGame("finished", log, cost)
