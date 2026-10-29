"""The v3 night: the two wolves talk in turn, up to a limit, and either can end the chat."""

import asyncio

from werewolf.agents.scripted import ScriptedAgent, policy
from werewolf.engine.actions import Agent, ChatAction, TargetAction, Task
from werewolf.engine.events import WolfChat
from werewolf.engine.game import play_game
from werewolf.engine.log import replays_exactly, to_log
from werewolf.engine.night import run_night
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings
from werewolf.engine.views import PlayerView
from werewolf.store.games import rule_version

TALK = Settings(wolf_chat_messages=5)


def wolves_of(state: GameState) -> list[str]:
    return [p.name for p in state.players if p.role is Role.WEREWOLF]


def table(seed: int) -> dict[str, Agent]:
    wolves = [p.name for p in new_game(seed).players if p.role is Role.WEREWOLF]
    return {p.name: policy(wolves) for p in new_game(seed).players}


def talkers(state: GameState, lines: list[str] | None = None) -> dict[str, Agent]:
    """Every wolf says the next line from a script, then nothing. Records who saw what."""
    queue = list(lines or [])
    seen: list[tuple[str, int]] = []

    def respond(view: PlayerView, task: Task) -> object:
        if task.kind == "wolf_chat":
            said = [e for e in view.events if isinstance(e, WolfChat) and e.round == view.round]
            seen.append((view.name, len(said)))
            return ChatAction(text=queue.pop(0) if queue else "more")
        if task.kind == "night_target":
            return TargetAction(target=task.options[0])
        raise AssertionError(task.kind)

    agents: dict[str, Agent] = {p.name: ScriptedAgent(respond) for p in state.players}
    agents["seen"] = seen  # type: ignore[assignment]
    return agents


def play(state: GameState, agents: dict[str, Agent]) -> list[WolfChat]:
    agents = {k: v for k, v in agents.items() if k != "seen"}
    asyncio.run(run_night(state, agents))
    return [e for e in state.events if isinstance(e, WolfChat)]


def test_the_wolves_talk_up_to_the_limit_taking_turns() -> None:
    state = new_game(seed=1, settings=TALK)
    first, second = wolves_of(state)
    chat = play(state, talkers(state))
    assert len(chat) == 5
    assert [m.speaker for m in chat] == [first, second, first, second, first]


def test_each_wolf_sees_what_was_said_before_it_speaks() -> None:
    state = new_game(seed=1, settings=TALK)
    agents = talkers(state)
    seen = agents["seen"]
    play(state, agents)
    assert [n for _, n in seen] == [0, 1, 2, 3, 4]  # type: ignore[attr-defined]


def test_the_wolf_who_opens_alternates_by_round() -> None:
    one = new_game(seed=1, settings=TALK)
    two = new_game(seed=1, settings=TALK)
    two.round = 2
    first, second = wolves_of(one)
    assert play(one, talkers(one))[0].speaker == first
    assert play(two, talkers(two))[0].speaker == second


def test_a_wolf_who_sends_nothing_ends_the_chat() -> None:
    state = new_game(seed=1, settings=TALK)
    chat = play(state, talkers(state, ["Let us take Eve.", "Agreed.", ""]))
    assert [m.text for m in chat] == ["Let us take Eve.", "Agreed."]


def test_a_chat_that_opens_with_nothing_is_empty() -> None:
    state = new_game(seed=1, settings=TALK)
    assert play(state, talkers(state, [""])) == []


def test_the_limit_is_a_setting() -> None:
    state = new_game(seed=1, settings=Settings(wolf_chat_messages=3))
    assert len(play(state, talkers(state))) == 3


def test_a_lone_wolf_has_nobody_to_talk_to() -> None:
    state = new_game(seed=1, settings=TALK)
    state.player(wolves_of(state)[1]).alive = False
    assert play(state, talkers(state)) == []


def test_zero_keeps_the_old_night_one_message_each_at_once() -> None:
    state = new_game(seed=1)
    assert state.settings.wolf_chat_messages == 0
    assert len(play(state, talkers(state))) == 2


def test_the_chat_is_private_to_the_wolves() -> None:
    state = new_game(seed=1, settings=TALK)
    play(state, talkers(state))
    wolves = set(wolves_of(state))
    assert all(set(e.audience or ()) == wolves for e in state.events if isinstance(e, WolfChat))


def test_old_settings_serialise_without_the_new_field_so_old_logs_keep_their_bytes() -> None:
    assert "wolf_chat_messages" not in Settings().model_dump_json()
    assert '"wolf_chat_messages":5' in TALK.model_dump_json()
    assert Settings.model_validate_json(Settings().model_dump_json()) == Settings()


def test_a_game_with_the_new_chat_is_a_v3_game_and_replays_exactly() -> None:
    state = asyncio.run(play_game(3, TALK, table(3)))
    log = to_log(state)
    assert rule_version(log) == "v3"
    assert replays_exactly(log)


def test_a_game_without_it_is_still_v2_or_v1() -> None:
    state = asyncio.run(play_game(3, Settings(), table(3)))
    assert rule_version(to_log(state)) == "v2"
