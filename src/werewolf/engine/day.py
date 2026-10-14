"""The day: one speaker per turn, chosen by floor-token bids, free bids, or a fixed order."""

from collections.abc import Callable, Mapping
from random import Random

from werewolf.engine.actions import Action, Agent, BidAction, BidTask
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.events import Listening, Speech
from werewolf.engine.record import check_cites
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


class DayRound:
    """One day's discussion. It holds what changes as the day goes: each player's floor tokens,
    how often each has spoken, and who is owed a free reply."""

    def __init__(self, state: GameState, agents: Mapping[str, Agent]) -> None:
        self.state = state
        self.agents = agents
        self.settings = state.settings
        self.floor = self.settings.speaking_mode is SpeakingMode.FLOOR_TOKENS
        self.alive = state.alive_names()
        self.limit = self.settings.max_message_chars
        # Fresh each day: tokens left over from yesterday are lost.
        self.tokens = {n: self.settings.tokens_per_day for n in self.alive}
        self.spoken = {n: 0 for n in self.alive}
        self.replied: set[str] = set()  # players who already got their one free reply today
        self.pending: tuple[str, str] | None = None  # (who owes a reply, who accused them)

    def listening(self, names: list[str]) -> None:
        self.state.events.extend(Listening(round=self.state.round, player=n) for n in names)

    def speech(self, speaker: str, action: BidAction, paid: int, reply: bool) -> Speech:
        """The posted message. Its cites are checked here: a wrong one is logged, not refused."""
        cites, invented = check_cites(action.cites, self.state.events)
        return Speech(
            round=self.state.round,
            speaker=speaker,
            text=action.message,
            paid=paid,
            reply=reply,
            cites=cites,
            invented=invented,
        )

    def accuse(self, action: BidAction, speaker: str) -> None:
        """If this message accused someone who has not had their reply yet, they get it next."""
        target = _new_accusation(action, speaker, self.alive, self.replied)
        if target:
            self.replied.add(target)
            self.pending = (target, speaker)

    async def free_turn(self, speaker: str, reply_to: str | None) -> BidAction | None:
        """Ask one player to speak at no cost. None means they stayed silent."""
        task = BidTask(max_bid=0, max_chars=self.limit, free=True, reply_to=reply_to)
        request = Request(speaker, task, bid_check(speaker, 0, self.limit, self.alive))
        (answer,) = await ask_many(self.state, self.agents, [request])
        action = _as_bid(answer)
        if not action.message.strip():
            self.listening([speaker])
            return None
        self.state.events.append(self.speech(speaker, action, 0, reply_to is not None))
        self.spoken[speaker] += 1
        return action

    async def reply_turn(self) -> None:
        assert self.pending is not None
        replier, accuser = self.pending
        self.pending = None
        action = await self.free_turn(replier, accuser)
        if action:
            self.accuse(action, replier)

    async def bidding_turn(self) -> bool:
        """Everyone bids in secret; the winner speaks. False when everyone chose to listen."""
        cap = {n: self.tokens[n] if self.floor else FREE_BID_MAX for n in self.alive}
        requests = [
            Request(
                n,
                BidTask(max_bid=cap[n], max_chars=self.limit),
                bid_check(n, cap[n], self.limit, self.alive),
            )
            for n in self.alive
        ]
        answers = await ask_many(self.state, self.agents, requests)
        actions = {n: _as_bid(a) for n, a in zip(self.alive, answers, strict=True)}
        bids = {n: a.bid for n, a in actions.items()}
        speaker = resolve_bids(self.alive, bids, self.spoken, self.state.rng)
        if speaker is None:
            self.listening(self.alive)
            return False
        action = actions[speaker]
        paid = action.bid if self.floor else 0
        self.state.events.append(self.speech(speaker, action, paid, False))
        self.tokens[speaker] -= paid
        self.spoken[speaker] += 1
        self.listening([n for n in self.alive if actions[n].bid == 0])
        if self.floor:  # the right of reply exists only with floor tokens
            self.accuse(action, speaker)
        return True

    async def run(self) -> None:
        if self.settings.speaking_mode is SpeakingMode.FIXED_ORDER:
            for turn in range(self.settings.speaking_turns):
                await self.free_turn(self.alive[turn % len(self.alive)], None)
            return
        for _ in range(self.settings.speaking_turns):
            if self.pending is not None:
                await self.reply_turn()
            elif not await self.bidding_turn():
                return


async def run_day(state: GameState, agents: Mapping[str, Agent]) -> None:
    await DayRound(state, agents).run()
