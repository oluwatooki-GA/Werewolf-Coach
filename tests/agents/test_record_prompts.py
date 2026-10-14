"""Numbered lines, cites, the game record in prompts, and rebuilding prompts from a saved game."""

import json
import re
from pathlib import Path

import pytest
from test_llm_agent import Rig
from test_prompt import build, state_with

from werewolf.agents.prompt import EXAMPLES, LEGEND
from werewolf.agents.prompter import Prompter
from werewolf.agents.wire import json_schema_for, to_action_json
from werewolf.cli import main
from werewolf.engine.actions import MemoryTask
from werewolf.engine.events import Death, Removal, Speech, VoteCast, WolfChat
from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.engine.setup import new_game
from werewolf.engine.views import make_view
from werewolf.promptview import rebuild, render
from werewolf.runner import (
    BatchReport,
    Played,
    cite_counts,
    cite_text,
    citing_messages,
    format_report,
    save_log,
)

CITING_BID = json.dumps(
    {
        "bid": 1,
        "message": "I quote someone",
        "intent": "none",
        "target": "",
        "note": "n",
        "beliefs": [],
        "cites": [{"line": "R1-1", "speaker": "Nobody"}],
    }
)


def said(round_: int, speaker: str, text: str = "hi", **kw: object) -> Speech:
    return Speech.model_validate(
        {"round": round_, "speaker": speaker, "text": text, "paid": 1, **kw}
    )


def test_each_public_message_starts_with_its_line_number() -> None:
    state = state_with(
        Death(round=1, player="Gus"),
        said(1, "Bo", "hi"),
        said(1, "Eve", "Not me", paid=0, reply=True),
        said(2, "Ada", "Again", paid=0),
    )
    text = build(state)[1]["content"]
    assert "[R1-1] Bo says (1 token): hi" in text
    assert "[R1-2] Eve replies (free): Not me" in text
    assert "[R2-1] Ada says: Again" in text
    assert "Morning: Gus was killed in the night." in text and "] Morning" not in text


def test_a_wolfs_private_chat_does_not_shift_the_numbers() -> None:
    chat = WolfChat(round=1, speaker="Fay", text="kill Di", audience=("Fay", "Hal"))
    state = state_with(said(1, "Bo", "one"), chat, said(1, "Cy", "two"))
    for who in ("Fay", "Cy"):  # Fay is a wolf in seed 1, Cy is not
        assert "[R1-2] Cy says (1 token): two" in build(state, who)[1]["content"]


def test_the_numbers_in_a_prompt_are_the_numbers_the_engine_checks() -> None:
    state = state_with(
        said(1, "Bo", "a"),
        said(1, "Cy", "b"),
        WolfChat(round=1, speaker="Fay", text="x", audience=("Fay", "Hal")),
        said(2, "Eve", "c"),
        said(2, "Bo", "d", paid=0, reply=True),
    )
    shown = re.findall(r"\[(R\d+-\d+)\] (\w+) (?:says|replies)", build(state)[1]["content"])
    assert shown == [(line, s.speaker) for line, s in numbered_speeches(state.events)]


def test_the_legend_explains_numbers_cites_and_the_record() -> None:
    assert "[R2-4]" in LEGEND and '"cites"' in LEGEND and "game record" in LEGEND
    assert "[R2-4]" in build(state_with())[0]["content"]


def test_the_game_record_stands_in_for_rounds_whose_log_is_hidden() -> None:
    state = state_with(
        Death(round=1, player="Gus"),
        said(1, "Di", "I am the Doctor."),
        VoteCast(round=1, voter="Bo", target="Di", reason="dodged"),
        Removal(round=1, player="Di"),
        said(2, "Bo", "Round two talk"),
    )
    state.round = 2
    text = build(state, from_round=2)[1]["content"]
    assert text.index("## Game record") < text.index("## What has happened")
    assert "Round 1: died in the night: Gus; claimed a role: Di Doctor (R1-1)" in text
    assert "votes: Di 1 (Bo); removed by the vote: Di." in text
    assert "Round 2: " not in text.split("## What has happened")[0]  # only finished-and-hidden


def test_there_is_no_record_while_the_whole_log_is_shown() -> None:
    state = state_with(said(1, "Bo", "x"))
    state.round = 2
    assert "## Game record" not in build(state, from_round=1)[1]["content"]
    state.round = 1
    assert "## Game record" not in build(state, from_round=1)[1]["content"]


def test_the_record_is_the_same_for_every_player() -> None:
    state = state_with(Death(round=1, player="Gus"), said(1, "Di", "I am the Doctor."))
    state.round = 2
    records = {
        build(state, who, from_round=2)[1]["content"].split("## What has happened")[0]
        for who in ("Cy", "Fay", "Di")
    }
    assert len(records) == 1


def test_the_memory_question_asks_for_reads_not_facts() -> None:
    asked = build(state_with(), task=MemoryTask(max_chars=800))[1]["content"]
    assert "your own reads" in asked and "do not copy them" in asked and "800 characters" in asked


def test_a_bid_answer_may_cite_lines_and_the_cites_reach_the_action() -> None:
    wire = {
        "bid": 1, "message": "Bo, you said that", "intent": "ask", "target": "Bo",
        "note": "n", "beliefs": [],
        "cites": [{"line": "R1-2", "speaker": "Bo"}],
    }  # fmt: skip
    action = json.loads(to_action_json("bid", json.dumps(wire)))
    assert action["cites"] == [{"line": "R1-2", "speaker": "Bo"}]


def test_a_bid_answer_without_cites_is_still_read() -> None:
    wire = {"bid": 0, "message": "", "intent": "none", "target": "", "note": "n", "beliefs": []}
    assert json.loads(to_action_json("bid", json.dumps(wire)))["cites"] == []


def test_the_schema_asks_for_cites_but_names_no_default() -> None:
    schema = json_schema_for("bid")
    assert "cites" in schema["required"] and "default" not in schema["properties"]["cites"]


def test_the_bid_example_shows_a_cite() -> None:
    assert '"cites":[{"line":"R1-2","speaker":"<name>"}]' in EXAMPLES["bid"]


def test_a_prompter_shows_what_it_learned_in_the_next_prompt() -> None:
    prompter = Prompter(summarize=True)
    view = make_view(new_game(seed=1), "Cy")
    task = MemoryTask(max_chars=800)
    prompter.learn("memory", json.dumps({"summary": "Bo seems honest"}))
    assert "Bo seems honest" in prompter.messages(view, task)[1]["content"]


def play_with_cites(tmp_path: Path, **kw: bool | int) -> tuple[Rig, GameLog]:
    rig = Rig(tmp_path)
    rig.model.raw["WireBid"] = CITING_BID
    return rig, rig.play(**kw)


@pytest.mark.parametrize("kw", [{}, {"summarize": True}, {"keep_notes": 2}])
def test_rebuilt_prompts_equal_the_prompts_the_players_were_sent(
    tmp_path: Path, kw: dict[str, bool | int]
) -> None:
    rig, log = play_with_cites(tmp_path, **kw)
    items = rebuild(log, keep_notes=int(kw.get("keep_notes", 0)))
    for player in {p.name for p in log.players}:
        sent = [m for name, m in rig.prompts if name == player]
        assert [i.messages for i in items if i.player == player] == sent


def test_the_rebuilt_prompts_include_retries_and_mark_posted_messages(tmp_path: Path) -> None:
    _, log = play_with_cites(tmp_path)
    items = rebuild(log)
    assert any(
        i.retry and "Your last answer was rejected" in i.messages[1]["content"] for i in items
    )
    posted = [i for i in items if i.spoke]
    assert posted and all(i.kind == "bid" for i in posted)


def test_render_prints_the_system_message_once_and_filters(tmp_path: Path) -> None:
    _, log = play_with_cites(tmp_path)
    text = render(rebuild(log), "Cy", round_=1, kind="bid")
    assert text.count("----- SYSTEM -----") == 1 and "===== Cy, round 1, bid" in text
    assert "===== Cy, round 1, vote" not in text
    assert "No prompt matches" in render(rebuild(log), "Nobody")


def test_show_prompt_prints_a_players_prompt_from_a_saved_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, log = play_with_cites(tmp_path)
    path = save_log(log, tmp_path / "games")
    assert main(["show", str(path), "--prompt", "Cy", "--round", "1", "--kind", "bid"]) == 0
    out = capsys.readouterr().out
    assert "===== Cy, round 1, bid" in out and "----- ANSWER -----" in out and "[R1-" in out


def test_invented_cites_are_counted_and_reported(tmp_path: Path) -> None:
    _, log = play_with_cites(tmp_path)
    messages, cited, invented = cite_counts([log])
    posted = [e for e in log.events if isinstance(e, Speech)]
    assert messages == len(posted) > 0
    assert cited == invented == len(posted)  # every posted message cited a line that is not there
    assert cite_text([log]) == f"{cited} cites in {messages} messages, invented {invented} (100.0%)"
    played = Played(1, "run", log, 1.0, [], tmp_path / "x.json")
    assert f"cites: {cite_text([log])}" in format_report(BatchReport(played=[played]))


def test_a_game_with_no_cites_says_so(tmp_path: Path) -> None:
    log = Rig(tmp_path).play()  # the fake model only ever listens
    assert cite_text([log]) == "no cites in 0 messages"


def test_the_report_says_how_many_messages_carry_a_cite(tmp_path: Path) -> None:
    _, log = play_with_cites(tmp_path)
    posted = cite_counts([log])[0]
    assert citing_messages([log]) == posted > 0  # the fake model cites in every message
    played = Played(1, "run", log, 1.0, [], tmp_path / "x.json")
    assert f"messages that cite: {posted} of {posted}" in format_report(
        BatchReport(played=[played])
    )
    assert citing_messages([Rig(tmp_path / "quiet").play()]) == 0
