"""The day: players bid floor tokens to speak, one speaker per turn."""

from collections.abc import Callable, Mapping
from random import Random

from werewolf.engine.actions import Action, Agent, BidAction, BidTask
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.events import Listening, Speech
from werewolf.engine.state import GameState


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
            return f"you can bid at most {max_bid} (the tokens you have left today)"
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
    alive = [p.name for p in state.players if p.alive]
    limit = settings.max_message_chars
    tokens = {n: settings.tokens_per_day for n in alive}  # fresh each day: leftovers are lost
    spoken = {n: 0 for n in alive}
    replied: set[str] = set()  # players who already got their one free reply today
    pending: tuple[str, str] | None = None  # (who owes a reply, who accused them)

    def listening(names: list[str]) -> None:
        state.events.extend(Listening(round=state.round, player=n) for n in names)

    for _ in range(settings.speaking_turns):
        if pending is not None:
            replier, accuser = pending
            pending = None
            task = BidTask(max_bid=0, max_chars=limit, reply_to=accuser)
            (answer,) = await ask_many(
                state, agents, [Request(replier, task, bid_check(replier, 0, limit, alive))]
            )
            action = _as_bid(answer)
            if not action.message.strip():
                listening([replier])
                continue
            state.events.append(
                Speech(round=state.round, speaker=replier, text=action.message, paid=0, reply=True)
            )
            spoken[replier] += 1
            target = _new_accusation(action, replier, alive, replied)
            if target:
                replied.add(target)
                pending = (target, replier)
            continue

        requests = [
            Request(
                n,
                BidTask(max_bid=tokens[n], max_chars=limit),
                bid_check(n, tokens[n], limit, alive),
            )
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
        state.events.append(
            Speech(round=state.round, speaker=speaker, text=action.message, paid=action.bid)
        )
        tokens[speaker] -= action.bid
        spoken[speaker] += 1
        listening([n for n in alive if actions[n].bid == 0])
        target = _new_accusation(action, speaker, alive, replied)
        if target:
            replied.add(target)
            pending = (target, speaker)
