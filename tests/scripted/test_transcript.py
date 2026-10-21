import asyncio
import json
from pathlib import Path

import pytest

from werewolf.agents.scripted import policy
from werewolf.cli import main
from werewolf.engine.events import (
    Death,
    GameOver,
    Listening,
    NightSummary,
    NoRemoval,
    Removal,
    SeerResult,
    Speech,
    VoteCast,
    WolfChat,
)
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.transcript import render

WOLVES = ["Fay", "Hal"]  # seed 1: Di Seer, Gus, Bo, Fay (wolf), Hal (wolf), Ada Doctor, Eve, Cy


def base_log() -> GameLog:
    agents = {p.name: policy(WOLVES) for p in new_game(1).players}
    return to_log(asyncio.run(play_game(1, None, agents)))


def story() -> GameLog:
    """The scripted game's players and stats, with a hand-written story."""
    events = [
        NightSummary(round=1, kill="Di", protect="Ada", check="Fay", saved=False, audience=()),
        WolfChat(round=1, speaker="Fay", text="Take Di tonight", audience=("Fay", "Hal")),
        SeerResult(round=1, target="Fay", role=Role.WEREWOLF, audience=("Di",)),
        Death(round=1, player="Di"),
        Speech(round=1, speaker="Bo", text="Who is the wolf?", paid=2),
        Listening(round=1, player="Cy"),
        Listening(round=1, player="Eve"),
        Speech(round=1, speaker="Fay", text="Not me, Bo.", paid=0, reply=True),
        Speech(round=1, speaker="Ada", text="Hmm.", paid=0),
        VoteCast(round=1, voter="Bo", target="Fay", reason="defensive"),
        VoteCast(round=1, voter="Cy", target=None, reason=""),
        Removal(round=1, player="Fay"),
        NoRemoval(round=2),
        GameOver(round=2, winner=Team.VILLAGE),
    ]
    return base_log().model_copy(update={"events": events})


def test_the_public_transcript_tells_the_story_a_watcher_would_see() -> None:
    text = render(story())
    assert "Round 1" in text
    assert "Morning: Di was killed" in text
    assert "Bo says (2 tokens): Who is the wolf?" in text
    assert "Fay replies (free): Not me, Bo." in text
    assert "Ada says: Hmm." in text
    assert "Listening: Cy, Eve" in text
    assert "Vote: Bo voted for Fay (reason: defensive)" in text
    assert "Vote: Cy abstained" in text
    assert "Fay was removed by the vote" in text
    assert "Nobody was removed by the vote" in text
    assert "Village wins" in text


def test_the_public_transcript_hides_every_secret() -> None:
    text = render(story())
    for secret in ("Take Di tonight", "Werewolf", "Seer", "Doctor", "protect", "checked"):
        assert secret not in text, secret
    assert "Villager" not in text


def test_the_private_transcript_adds_roles_wolf_chat_and_what_really_happened_at_night() -> None:
    text = render(story(), private=True)
    assert "Fay=Werewolf" in text and "Di=Seer" in text
    assert "[wolf chat] Fay: Take Di tonight" in text
    assert "[seer] Di checked Fay: Werewolf" in text
    assert "Night: the wolves chose Di, the Doctor protected Ada, the Seer checked Fay" in text


def test_the_private_transcript_lists_each_players_private_notes() -> None:
    log = story()
    answer = json.dumps({"target": "Di", "note": "Di is too dangerous", "beliefs": {}})
    call = log.calls[0].model_copy(update={"responses": [answer], "player": "Fay"})
    text = render(log.model_copy(update={"calls": [call, *log.calls[1:]]}), private=True)
    assert "Private notes" in text and "Fay" in text and "Di is too dangerous" in text
    assert "Di is too dangerous" not in render(log.model_copy(update={"calls": [call]}))


def test_the_footer_reports_the_cost_and_the_answers() -> None:
    text = render(story())
    assert "calls" in text and "rejected" in text and "cost $" in text


def test_a_real_scripted_game_renders_without_a_story() -> None:
    text = render(base_log())
    assert "Village wins" in text and "Round 2" in text


def test_the_show_command_prints_a_saved_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "g.json"
    path.write_bytes(base_log().to_json().encode())
    assert main(["show", str(path)]) == 0
    assert "Village wins" in capsys.readouterr().out
    assert main(["show", str(path), "--private"]) == 0
    assert "Fay=Werewolf" in capsys.readouterr().out


def test_the_show_command_reports_an_unreadable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["show", str(tmp_path / "nope.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_talk_only_shows_just_the_messages_and_the_votes() -> None:
    text = render(story(), talk_only=True)
    for line in (
        "Bo says (2 tokens): Who is the wolf?",
        "Fay replies (free): Not me, Bo.",
        "Ada says: Hmm.",
        "Vote: Bo voted for Fay (reason: defensive).",
        "Vote: Cy abstained.",
        "Fay was removed by the vote.",
        "Nobody was removed by the vote.",
    ):
        assert line in text, line


def test_talk_only_leaves_out_everything_else() -> None:
    text = render(story(), talk_only=True)
    for left_out in ("Morning", "Listening", "Game:", "Players:", "calls", "Game over", "cost $"):
        assert left_out not in text, left_out
    assert "wolf chat" not in text and "Take Di tonight" not in text


def test_talk_only_keeps_the_round_headings() -> None:
    text = render(story(), talk_only=True)
    assert text.startswith("=== Round 1 ===") and "=== Round 2 ===" in text


def test_talk_only_stays_public_even_when_private_is_asked_for() -> None:
    text = render(story(), private=True, talk_only=True)
    assert "Take Di tonight" not in text and "Werewolf" not in text


def test_the_show_command_has_a_talk_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "g.json"
    path.write_bytes(story().to_json().encode())
    assert main(["show", str(path), "--talk"]) == 0
    out = capsys.readouterr().out
    assert "Bo says (2 tokens): Who is the wolf?" in out and "Players:" not in out


def night(round_: int, kill: str | None, protect: str | None, check: str | None) -> NightSummary:
    return NightSummary(
        round=round_, kill=kill, protect=protect, check=check, saved=False, audience=()
    )


def test_a_dead_seer_or_doctor_is_named_as_dead_not_as_checking_nobody() -> None:
    events = [
        night(1, "Di", "Ada", "Fay"),
        Death(round=1, player="Di"),  # the Seer is killed
        night(2, "Ada", None, None),
        Death(round=2, player="Ada"),  # the Doctor is killed
        night(3, "Bo", None, None),
    ]
    text = render(story().model_copy(update={"events": events}), private=True)
    assert "Night: the wolves chose Di, the Doctor protected Ada, the Seer checked Fay" in text
    assert "the Doctor protected nobody, the Seer was killed in round 1" in text
    assert "the Doctor was killed in round 2, the Seer was killed in round 1" in text


def test_a_seer_who_was_voted_out_says_so_and_a_living_one_who_did_not_check_says_nobody() -> None:
    events = [
        night(1, "Bo", "Ada", None),
        Removal(round=1, player="Di"),
        night(2, "Cy", "Ada", None),
    ]
    text = render(story().model_copy(update={"events": events}), private=True)
    assert "the Seer checked nobody" in text  # round 1: alive, did not check
    assert "the Seer was voted out in round 1" in text  # round 2
