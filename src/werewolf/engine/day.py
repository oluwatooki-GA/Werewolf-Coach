"""The day: one speaker per turn, chosen by floor-token bids, free bids, or a fixed order."""

from collections.abc import Callable, Mapping
from random import Random

from werewolf.engine.actions import Action, Agent, BidAction, BidTask
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.events import Listening, Speech
from werewolf.engine.state import GameState, SpeakingMode

FREE_BID_MAX = 4  # Werewolf Arena's free bid: 0 to 4, no cost


def resolve_bids(
    order: list[str], bids: Mapping[str, int], spoken: Mapping[str, int], rng: Random
) -> str | None:
    """Highest bid speaks. Ties go to whoever has spoken least today, then to the rng."""
    live = {n: b for n, b in bids.items() if b > 0}
    if not live:
        return None
    top = max(live.values())
    tied = [n for n in order if live.get(n) == top]
    least = min(spoken[n] for n in tied)
    candidates = [n for n in tied if spoken[n] == least]
    return candidates[0] if len(candidates) == 1 else rng.choice(candidates)


def bid_check(
    me: str, max_bid: int, limit: int, alive: list[str]
) -> Callable[[Action], str | None]:
    def check(action: Action) -> str | None:
        if not isinstance(action, BidAction):
            return "expected a bid"
        if action.bid > max_bid:
            return f"you can bid at most {max_bid}"
        if len(action.message) > limit:
            return f"the message must be at most {limit} characters"
        if action.bid > 0 and not action.message.strip():
            return "a bid above 0 needs a message"
        if action.target is not None and (action.target == me or action.target not in alive):
            return "the target must be another living player"
        return None

    return check


def _as_bid(action: Action) -> BidAction:
    return action if isinstance(action, BidAction) else BidAction(bid=0)


def _new_accusation(
    action: BidAction, speaker: str, alive: list[str], replied: set[str]
) -> str | None:
    target = action.target
    if action.intent == "accuse" and target and target != speaker and target in alive:
        return target if target not in replied else None
    return None


async def run_day(state: GameState, agents: Mapping[str, Agent]) -> None:
    settings = state.settings
    floor = settings.speaking_mode is SpeakingMode.FLOOR_TOKENS
    alive = state.alive_names()
    limit = settings.max_message_chars
    tokens = {n: settings.tokens_per_day for n in alive}  # fresh each day: leftovers are lost
    spoken = {n: 0 for n in alive}
    replied: set[str] = set()  # players who already got their one free reply today
    pending: tuple[str, str] | None = None  # (who owes a reply, who accused them)

    def listening(names: list[str]) -> None:
        state.events.extend(Listening(round=state.round, player=n) for n in names)

    async def free_turn(speaker: str, reply_to: str | None) -> BidAction | None:
        """Ask one player to speak at no cost. None means they stayed silent."""
        task = BidTask(max_bid=0, max_chars=limit, free=True, reply_to=reply_to)
        request = Request(speaker, task, bid_check(speaker, 0, limit, alive))
        (answer,) = await ask_many(state, agents, [request])
        action = _as_bid(answer)
        if not action.message.strip():
            listening([speaker])
            return None
        state.events.append(
            Speech(
                round=state.round,
                speaker=speaker,
                text=action.message,
                paid=0,
                reply=reply_to is not None,
            )
        )
        spoken[speaker] += 1
        return action

    if settings.speaking_mode is SpeakingMode.FIXED_ORDER:
        for turn in range(settings.speaking_turns):
            await free_turn(alive[turn % len(alive)], None)
        return

    for _ in range(settings.speaking_turns):
        if pending is not None:
            replier, accuser = pending
            pending = None
            action = await free_turn(replier, accuser)
            target = _new_accusation(action, replier, alive, replied) if action else None
            if target:
                replied.add(target)
                pending = (target, replier)
            continue

        cap = {n: tokens[n] if floor else FREE_BID_MAX for n in alive}
        requests = [
            Request(n, BidTask(max_bid=cap[n], max_chars=limit), bid_check(n, cap[n], limit, alive))
            for n in alive
        ]
        actions = {
            n: _as_bid(a)
            for n, a in zip(alive, await ask_many(state, agents, requests), strict=True)
        }
        speaker = resolve_bids(alive, {n: a.bid for n, a in actions.items()}, spoken, state.rng)
        if speaker is None:
            listening(alive)
            return
        action = actions[speaker]
        paid = action.bid if floor else 0
        state.events.append(
            Speech(round=state.round, speaker=speaker, text=action.message, paid=paid)
        )
        tokens[speaker] -= paid
        spoken[speaker] += 1
        listening([n for n in alive if actions[n].bid == 0])
        target = _new_accusation(action, speaker, alive, replied) if floor else None
        if target:
            replied.add(target)
            pending = (target, speaker)
