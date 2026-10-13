import asyncio
import json
from pathlib import Path

from test_llm_agent import MODEL, Rig

from werewolf.agents.llm_agent import LLMAgent
from werewolf.agents.prompt import build_messages, estimate_tokens
from werewolf.engine.actions import BidTask, MemoryTask
from werewolf.engine.events import Death, Event, Speech
from werewolf.engine.setup import new_game
from werewolf.engine.views import make_view

MEMORY = MemoryTask(max_chars=800)
BID = BidTask(max_bid=3, max_chars=300)


def agent_in(tmp_path: Path, summarize: bool = True) -> tuple[LLMAgent, Rig]:
    rig = Rig(tmp_path)
    agent = LLMAgent(
        "Cy",
        rig.client,
        MODEL,
        summarize=summarize,
        on_prompt=lambda name, messages: rig.prompts.append((name, messages)),
    )
    return agent, rig


def view_in_round(round_: int, *events: Event):
    state = new_game(seed=1)
    state.events.extend(events)
    state.round = round_
    return make_view(state, "Cy")


def remember(agent: LLMAgent, rig: Rig, summary: str) -> None:
    rig.model.raw["WireMemory"] = json.dumps({"summary": summary})
    asyncio.run(agent.act(view_in_round(1), MEMORY))


def next_prompt(agent: LLMAgent, rig: Rig, round_: int = 2, *events: Event) -> str:
    asyncio.run(agent.act(view_in_round(round_, *events), BID))
    return rig.prompts[-1][1][1]["content"]


def test_a_summary_is_remembered_and_shown_in_the_next_prompt(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    remember(agent, rig, "Round 1: Gus died.")
    assert "Summary of earlier rounds: Round 1: Gus died." in next_prompt(agent, rig)


def test_a_new_summary_replaces_the_old_one(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    remember(agent, rig, "first version")
    remember(agent, rig, "second version")
    text = next_prompt(agent, rig)
    assert "second version" in text and "first version" not in text


def test_an_empty_summary_keeps_the_old_one(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    remember(agent, rig, "keep me")
    remember(agent, rig, "")
    assert "keep me" in next_prompt(agent, rig)


def test_an_unreadable_summary_keeps_the_old_one(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    remember(agent, rig, "keep me")
    rig.model.raw["WireMemory"] = "not json at all"
    asyncio.run(agent.act(view_in_round(1), MEMORY))
    assert "keep me" in next_prompt(agent, rig)


def test_with_summaries_on_only_the_current_round_is_shown(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    events = (Death(round=1, player="Gus"), Death(round=2, player="Bo"))
    text = next_prompt(agent, rig, 2, *events)
    assert "Gus was killed" not in text and "Bo was killed" in text


def test_with_summaries_off_the_whole_log_is_shown(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path, summarize=False)
    events = (Death(round=1, player="Gus"), Death(round=2, player="Bo"))
    text = next_prompt(agent, rig, 2, *events)
    assert "Gus was killed" in text and "Bo was killed" in text


def test_the_memory_question_asks_for_a_short_summary_within_the_limit(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    remember(agent, rig, "x")
    asked = rig.prompts[-1][1][1]["content"]
    assert (
        "summary" in asked.lower() and "800 characters" in asked and "JSON fields: summary" in asked
    )


def test_the_prompt_stops_growing_once_older_rounds_are_summarised() -> None:
    def round_events(r: int) -> list[Event]:
        return [Speech(round=r, speaker="Bo", text="x" * 200, paid=1) for _ in range(20)]

    def size(round_: int, windowed: bool) -> int:
        events = [e for r in range(1, round_ + 1) for e in round_events(r)]
        view = view_in_round(round_, *events)
        messages = build_messages(
            view, BID, summary="s" * 800, from_round=round_ if windowed else 1
        )
        return estimate_tokens(messages)

    windowed = [size(r, True) for r in range(2, 6)]
    whole = [size(r, False) for r in range(2, 6)]
    assert max(windowed) - min(windowed) < 0.1 * min(windowed)  # flat
    assert whole[-1] > 2 * whole[0]  # without it, the prompt keeps growing
