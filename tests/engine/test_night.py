import asyncio

from werewolf.agents.scripted import ScriptedAgent
from werewolf.engine.actions import Agent, ChatAction, TargetAction, Task
from werewolf.engine.events import Death, NightSummary, NoDeath, SeerResult, WolfChat
from werewolf.engine.night import run_night
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState
from werewolf.engine.views import PlayerView, make_view


def who(state: GameState, role: Role, n: int = 0) -> str:
    return [p.name for p in state.players if p.role is role][n]


def night_agents(
    state: GameState,
    kill: str | None = None,
    check: str | None = None,
    protect: str | None = None,
    chat: str = "hi",
) -> dict[str, Agent]:
    def respond(view: PlayerView, task: Task) -> object:
        if task.kind == "wolf_chat":
            return ChatAction(text=chat)
        if task.kind == "night_target":
            choice = {"kill": kill, "check": check, "protect": protect}[task.purpose]
            return TargetAction(target=choice)
        raise AssertionError(f"unexpected task {task.kind}")

    return {p.name: ScriptedAgent(respond) for p in state.players}


def play_night(state: GameState, agents: dict[str, Agent]) -> None:
    asyncio.run(run_night(state, agents))


def events_of[E](state: GameState, kind: type[E]) -> list[E]:
    return [e for e in state.events if isinstance(e, kind)]


def picks(target: str | None) -> ScriptedAgent:
    """A wolf that says a word in the chat and always names the same kill target."""

    def respond(view: PlayerView, task: Task) -> object:
        if task.kind == "wolf_chat":
            return ChatAction(text="x")
        return TargetAction(target=target)

    return ScriptedAgent(respond)


class SlowAgent:
    def __init__(self, inner: Agent) -> None:
        self._inner = inner

    async def act(self, view: PlayerView, task: Task) -> object:
        await asyncio.sleep(0.05)
        return await self._inner.act(view, task)


def alive(state: GameState, name: str) -> bool:
    return next(p for p in state.players if p.name == name).alive


def test_an_unprotected_target_dies_and_the_morning_announces_it() -> None:
    state = new_game(seed=1)
    victim = who(state, Role.VILLAGER)
    play_night(state, night_agents(state, kill=victim))
    assert not alive(state, victim)
    assert events_of(state, Death) == [Death(round=1, player=victim)]


def test_a_protected_target_survives_and_nobody_dies() -> None:
    state = new_game(seed=1)
    victim = who(state, Role.VILLAGER)
    play_night(state, night_agents(state, kill=victim, protect=victim))
    assert alive(state, victim)
    assert events_of(state, NoDeath) == [NoDeath(round=1)]
    assert events_of(state, Death) == []


def test_the_doctor_may_protect_herself() -> None:
    state = new_game(seed=1)
    doctor = who(state, Role.DOCTOR)
    play_night(state, night_agents(state, kill=doctor, protect=doctor))
    assert alive(state, doctor)


def test_protecting_someone_else_does_not_save_the_target() -> None:
    state = new_game(seed=1)
    victim, other = [p.name for p in state.players if p.role is Role.VILLAGER][:2]
    play_night(state, night_agents(state, kill=victim, protect=other))
    assert not alive(state, victim)


def test_the_seer_learns_the_true_role_and_only_the_seer_sees_it() -> None:
    state = new_game(seed=1)
    seer, wolf = who(state, Role.SEER), who(state, Role.WEREWOLF)
    play_night(state, night_agents(state, check=wolf))
    result = SeerResult(round=1, target=wolf, role=Role.WEREWOLF, audience=(seer,))
    assert events_of(state, SeerResult) == [result]
    for p in state.players:
        seen = [e for e in make_view(state, p.name).events if isinstance(e, SeerResult)]
        assert seen == ([result] if p.name == seer else [])


def test_the_wolf_chat_is_seen_only_by_wolves() -> None:
    state = new_game(seed=1)
    play_night(state, night_agents(state, chat="SECRET-PLAN"))
    for p in state.players:
        text = make_view(state, p.name).model_dump_json()
        assert ("SECRET-PLAN" in text) == (p.role is Role.WEREWOLF)


def test_wolves_write_their_chat_messages_without_seeing_each_other() -> None:
    state = new_game(seed=1)
    first, second = who(state, Role.WEREWOLF, 0), who(state, Role.WEREWOLF, 1)
    seen: list[list[str]] = []

    def listener(view: PlayerView, task: Task) -> object:
        if task.kind == "wolf_chat":
            seen.append([e.text for e in view.events if isinstance(e, WolfChat)])
            return ChatAction(text="second")
        return TargetAction(target=None)

    agents = night_agents(state, chat="first")
    agents[second] = ScriptedAgent(listener)
    play_night(state, agents)
    assert seen == [[]]  # asked at the same time: no copying the partner's pick
    assert [e.speaker for e in events_of(state, WolfChat)] == [first, second]


def test_disagreeing_wolves_are_settled_by_the_seeded_rng() -> None:
    def outcome(seed: int) -> str:
        """Which wolf's choice won: 'first' or 'second'."""
        state = new_game(seed=seed)
        a, b = [p.name for p in state.players if p.role is Role.VILLAGER][:2]
        agents = night_agents(state)
        agents[who(state, Role.WEREWOLF, 0)] = picks(a)
        agents[who(state, Role.WEREWOLF, 1)] = picks(b)
        play_night(state, agents)
        victim = events_of(state, Death)[0].player
        return "first" if victim == a else "second"

    assert all(outcome(seed) == outcome(seed) for seed in range(8))
    assert len({outcome(seed) for seed in range(20)}) == 2


def test_if_one_wolf_abstains_the_other_wolfs_target_stands() -> None:
    state = new_game(seed=1)
    victim = who(state, Role.VILLAGER)
    wolf2 = who(state, Role.WEREWOLF, 1)
    agents = night_agents(state, kill=victim)
    agents[wolf2] = picks(None)
    play_night(state, agents)
    assert not alive(state, victim)


def test_if_both_wolves_abstain_nobody_dies() -> None:
    state = new_game(seed=1)
    play_night(state, night_agents(state, kill=None))
    assert all(p.alive for p in state.players)
    assert events_of(state, NoDeath) == [NoDeath(round=1)]


def test_a_dead_seer_and_doctor_are_not_asked_to_act() -> None:
    state = new_game(seed=1)
    gone = [who(state, Role.SEER), who(state, Role.DOCTOR)]
    for p in state.players:
        if p.name in gone:
            p.alive = False

    def never(view: PlayerView, task: Task) -> object:
        raise AssertionError("a dead player was asked")

    agents = night_agents(state, kill=who(state, Role.VILLAGER))
    for name in gone:
        agents[name] = ScriptedAgent(never)
    play_night(state, agents)
    assert state.calls
    assert all(c.player not in gone for c in state.calls)


def test_a_lone_wolf_does_not_chat_and_still_kills() -> None:
    state = new_game(seed=1)
    dead_wolf = who(state, Role.WEREWOLF, 1)
    next(p for p in state.players if p.name == dead_wolf).alive = False
    victim = who(state, Role.VILLAGER)
    play_night(state, night_agents(state, kill=victim))
    assert events_of(state, WolfChat) == []
    assert not alive(state, victim)


def test_a_wolf_cannot_target_its_partner() -> None:
    state = new_game(seed=1)
    partner = who(state, Role.WEREWOLF, 1)
    victim = who(state, Role.VILLAGER)
    wolf1 = who(state, Role.WEREWOLF, 0)
    errors: list[str | None] = []

    def respond(view: PlayerView, task: Task) -> object:
        if task.kind == "wolf_chat":
            return ChatAction(text="x")
        errors.append(task.error)
        return TargetAction(target=partner if task.error is None else victim)

    agents = night_agents(state, kill=victim)
    agents[wolf1] = ScriptedAgent(respond)
    play_night(state, agents)
    assert errors[0] is None and errors[1] is not None
    assert alive(state, partner)
    record = next(c for c in state.calls if c.player == wolf1 and c.task["kind"] == "night_target")
    assert (record.rejected, record.failed) == (1, False)


def test_an_overlong_wolf_message_is_rejected() -> None:
    state = new_game(seed=1)
    play_night(state, night_agents(state, chat="x" * 301))
    record = next(c for c in state.calls if c.task["kind"] == "wolf_chat")
    assert record.failed and record.rejected == 2
    assert events_of(state, WolfChat) == []


def test_the_night_summary_is_kept_for_analysis_but_shown_to_nobody() -> None:
    state = new_game(seed=1)
    victim, seer_target = who(state, Role.VILLAGER), who(state, Role.DOCTOR)
    play_night(state, night_agents(state, kill=victim, check=seer_target, protect=victim))
    summary = events_of(state, NightSummary)[0]
    assert (summary.kill, summary.protect, summary.check, summary.saved) == (
        victim, victim, seer_target, True
    )  # fmt: skip
    for p in state.players:
        assert all(e.kind != "night_summary" for e in make_view(state, p.name).events)


def test_the_announcement_never_names_a_role() -> None:
    state = new_game(seed=1)
    victim = who(state, Role.SEER)
    play_night(state, night_agents(state, kill=victim))
    announcement = events_of(state, Death)[0].model_dump_json()
    assert not any(role.value in announcement for role in Role)


def test_calls_are_recorded_in_a_fixed_order_whatever_the_answer_speed() -> None:
    def order(slow_role: Role) -> list[str]:
        state = new_game(seed=1)
        agents = night_agents(state, kill=who(state, Role.VILLAGER))
        slow = who(state, slow_role)
        agents[slow] = SlowAgent(agents[slow])
        play_night(state, agents)
        return [f"{c.player}:{c.task['kind']}" for c in state.calls]

    assert order(Role.WEREWOLF) == order(Role.DOCTOR)
