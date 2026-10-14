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


def agent_in(tmp_path: Path, summarize: bool = True, keep_notes: int = 0) -> tuple[LLMAgent, Rig]:
    rig = Rig(tmp_path)
    agent = LLMAgent(
        "Cy",
        rig.client,
        MODEL,
        summarize=summarize,
        keep_notes=keep_notes,
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
    assert whole[-1] - whole[0] >= 2500  # without it, every extra round adds about 1,000 tokens


def think(agent: LLMAgent, rig: Rig, note: str) -> None:
    rig.model.note_for["Cy"] = note
    asyncio.run(agent.act(view_in_round(1), BID))


def test_with_notes_on_the_agent_is_shown_its_own_last_notes(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path, keep_notes=2)
    for note in ("first thought", "second thought", "third thought"):
        think(agent, rig, note)
    text = next_prompt(agent, rig)
    assert "second thought" in text and "third thought" in text
    assert "first thought" not in text  # only the last two are kept
    assert text.index("second thought") < text.index("third thought")


def test_with_notes_off_the_prompt_has_no_notes_section(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path)
    think(agent, rig, "a private thought")
    assert "Your recent private notes" not in next_prompt(agent, rig)


def test_the_note_of_an_unreadable_answer_is_not_kept(tmp_path: Path) -> None:
    agent, rig = agent_in(tmp_path, keep_notes=2)
    rig.model.raw["WireBid"] = '{"note": "kept? no", "bid":'
    asyncio.run(agent.act(view_in_round(1), BID))
    rig.model.raw.clear()
    assert "kept? no" not in next_prompt(agent, rig)
