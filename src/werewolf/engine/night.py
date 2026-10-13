"""The night: wolves chat and choose a victim, the Seer checks, the Doctor protects."""
from collections.abc import Callable, Mapping

from werewolf.engine.actions import (
    Action,
    Agent,
    ChatAction,
    NightTargetTask,
    TargetAction,
    WolfChatTask,
)
from werewolf.engine.calls import Request, ask_many
from werewolf.engine.events import Death, NightSummary, NoDeath, SeerResult, WolfChat
from werewolf.engine.roles import Role
from werewolf.engine.state import GameState


def target_check(options: tuple[str, ...]) -> Callable[[Action], str | None]:
    def check(action: Action) -> str | None:
        if isinstance(action, TargetAction) and (action.target is None or action.target in options):
            return None
        return f"the target must be one of: {', '.join(options)} (or no target)"

    return check


def chat_check(limit: int) -> Callable[[Action], str | None]:
    def check(action: Action) -> str | None:
        if isinstance(action, ChatAction) and len(action.text) <= limit:
            return None
        return f"the message must be at most {limit} characters"

    return check


def _target(action: Action) -> str | None:
    return action.target if isinstance(action, TargetAction) else None


async def run_night(state: GameState, agents: Mapping[str, Agent]) -> None:
    alive = [p for p in state.players if p.alive]
    wolves = tuple(p.name for p in alive if p.role is Role.WEREWOLF)
    seer = next((p.name for p in alive if p.role is Role.SEER), None)
    doctor = next((p.name for p in alive if p.role is Role.DOCTOR), None)
    limit = state.settings.max_message_chars

    if len(wolves) == 2:  # a lone wolf has nobody to talk to
        for wolf in wolves:
            (reply,) = await ask_many(
                state, agents, [Request(wolf, WolfChatTask(max_chars=limit), chat_check(limit))]
            )
            if isinstance(reply, ChatAction) and reply.text:
                state.events.append(
                    WolfChat(round=state.round, speaker=wolf, text=reply.text, audience=wolves)
                )

    names = tuple(p.name for p in alive)
    prey = tuple(p.name for p in alive if p.role is not Role.WEREWOLF)
    requests = [
        Request(w, NightTargetTask(purpose="kill", options=prey), target_check(prey))
        for w in wolves
    ]
    if seer:
        options = tuple(n for n in names if n != seer)
        requests.append(
            Request(seer, NightTargetTask(purpose="check", options=options), target_check(options))
        )
    if doctor:
        requests.append(
            Request(doctor, NightTargetTask(purpose="protect", options=names), target_check(names))
        )
    answers = await ask_many(state, agents, requests)

    votes = [t for t in (_target(a) for a in answers[: len(wolves)]) if t]
    kill = state.rng.choice(votes) if len(set(votes)) > 1 else (votes[0] if votes else None)
    check = _target(answers[len(wolves)]) if seer else None
    protect = _target(answers[-1]) if doctor else None

    if seer and check:
        found = next(p for p in state.players if p.name == check)
        result = SeerResult(round=state.round, target=check, role=found.role, audience=(seer,))
        state.events.append(result)

    saved = kill is not None and kill == protect
    state.events.append(
        NightSummary(
            round=state.round, kill=kill, protect=protect, check=check, saved=saved, audience=()
        )
    )
    if kill is not None and not saved:
        next(p for p in state.players if p.name == kill).alive = False
        state.events.append(Death(round=state.round, player=kill))
    else:
        state.events.append(NoDeath(round=state.round))
