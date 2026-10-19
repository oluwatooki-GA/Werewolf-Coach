"""Card adherence on hand-made games, with the numbers worked out by hand."""

import json
from pathlib import Path

import pytest
from test_derive import VILLAGER, WOLF_A, base_log
from test_tagger import talk

from werewolf.cli import main
from werewolf.engine.log import GameLog
from werewolf.engine.state import CallRecord
from werewolf.tagger.adherence import adherence, format_adherence, wilson
from werewolf.tagger.tags import Tag, TagFile, save_tags


@pytest.fixture(autouse=True)
def in_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[2])  # the real cards/ folder


def bid(player: str, message: str, intent: str) -> CallRecord:
    answer = {"bid": 1, "message": message, "intent": intent, "target": None}
    return CallRecord(
        round=1, player=player, task={"kind": "bid", "max_bid": 3, "free": False},
        responses=[json.dumps(answer)], errors=[], rejected=0, failed=False,
    )  # fmt: skip


def tag(speaker: str, line: str, *moves: str) -> Tag:
    return Tag(line=line, speaker=speaker, round=1, moves=moves)


def game(card_seats: dict[str, str]) -> GameLog:
    log = base_log(talk((WOLF_A, "M1"), (WOLF_A, "M2"), (WOLF_A, "M3"), (VILLAGER, "M4")))
    calls = [bid(WOLF_A, "M1", "accuse"), bid(WOLF_A, "M2", "accuse"), bid(WOLF_A, "M3", "defend")]
    return log.model_copy(
        update={"calls": calls, "settings": log.settings.model_copy(update={"cards": card_seats})}
    )


TAGS = TagFile(
    model="m",
    tags=[
        tag(WOLF_A, "R1-1", "hedge"),  # expected move; intent accuse does not fit hedge
        tag(WOLF_A, "R1-2", "accuse_bare"),  # not an expected move; fits the accuse intent
        tag(WOLF_A, "R1-3", "self_defend"),  # expected; fits the defend intent
        tag(VILLAGER, "R1-4", "hedge"),  # another seat: ignored
    ],
)


def test_adherence_and_intent_agreement_equal_the_hand_worked_numbers() -> None:
    stats = adherence([(game({WOLF_A: "wolf.lie_low@1"}), TAGS)])
    card = stats["wolf.lie_low"]
    assert (card.games, card.messages, card.adhering) == (1, 3, 2)
    assert (card.with_intent, card.intent_match) == (3, 2)


def test_two_games_add_up() -> None:
    log = game({WOLF_A: "wolf.lie_low@1"})
    card = adherence([(log, TAGS), (log, TAGS)])["wolf.lie_low"]
    assert (card.games, card.messages, card.adhering) == (2, 6, 4)


def test_a_card_with_no_tagged_messages_says_no_data_and_a_game_without_cards_adds_nothing() -> (
    None
):
    bare = TagFile(model="m", tags=[])
    stats = adherence([(game({WOLF_A: "wolf.lie_low@1"}), bare), (game({}), TAGS)])
    assert "no data" in format_adherence(stats)
    assert list(stats) == ["wolf.lie_low"]
    assert format_adherence({}) == "no tagged games with cards"


def test_the_report_is_the_same_every_time() -> None:
    games = [(game({WOLF_A: "wolf.lie_low@1"}), TAGS)]
    assert format_adherence(adherence(games)) == format_adherence(adherence(games))


def test_the_interval_is_zero_width_for_no_data_and_sensible_for_five_of_ten() -> None:
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(5, 10)
    assert 0.23 < low < 0.24 and 0.76 < high < 0.77
    assert wilson(10, 10)[1] == 1.0 and wilson(0, 10)[0] == 0.0


def test_the_command_reads_tag_files_and_names_games_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tagged, untagged = tmp_path / "1-a.json", tmp_path / "2-b.json"
    log = game({WOLF_A: "wolf.lie_low@1"})
    for path in (tagged, untagged):
        path.write_bytes(log.to_json().encode("utf-8"))
    save_tags(tagged, TAGS)
    assert main(["adherence", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "wolf.lie_low" in out and "67% (2/3" in out
    assert "1 game(s) left out" in out
