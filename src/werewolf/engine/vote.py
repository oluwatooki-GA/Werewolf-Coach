"""The vote: everyone votes at once, the votes are shown together, the most votes is removed."""

from collections import Counter
from collections.abc import Callable, Mapping

from werewolf.engine.actions import Action, Agent, VoteAction, VoteTask
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.events import NoRemoval, Removal, VoteCast
from werewolf.engine.state import GameState


def vote_check(options: tuple[str, ...], limit: int) -> Callable[[Action], str | None]:
    def check(action: Action) -> str | None:
        if not isinstance(action, VoteAction):
            return "expected a vote"
        if action.target is not None and action.target not in options:
            return f"vote for one of: {', '.join(options)} (or abstain)"
        if len(action.reason) > limit:
            return f"the reason must be at most {limit} characters"
        return None

    return check


async def run_vote(state: GameState, agents: Mapping[str, Agent]) -> None:
    alive = [p.name for p in state.players if p.alive]
    limit = state.settings.max_message_chars
    requests = []
    for name in alive:
        options = tuple(n for n in alive if n != name)
        requests.append(Request(name, VoteTask(options=options), vote_check(options, limit)))
    answers = await ask_many(state, agents, requests)

    tally: Counter[str] = Counter()
    for name, answer in zip(alive, answers, strict=True):
        vote = answer if isinstance(answer, VoteAction) else VoteAction(target=None)
        state.events.append(
            VoteCast(round=state.round, voter=name, target=vote.target, reason=vote.reason)
        )
        if vote.target is not None:
            tally[vote.target] += 1

    top = tally.most_common(2)
    if top and (len(top) == 1 or top[0][1] > top[1][1]):
        out = top[0][0]
        next(p for p in state.players if p.name == out).alive = False
        state.events.append(Removal(round=state.round, player=out))
    else:
        state.events.append(NoRemoval(round=state.round))
