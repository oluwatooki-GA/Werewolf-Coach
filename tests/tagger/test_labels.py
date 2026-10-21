"""Labeling messages by hand, and scoring the tagger against those labels."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from test_derive import VILLAGER, WOLF_A, base_log
from test_tagger import talk

from werewolf.cli import main
from werewolf.tagger.labels import (
    Label,
    accuracy,
    collect,
    format_accuracy,
    load_labels,
    run_session,
    sample,
)
from werewolf.tagger.moves import MOVE_NAMES
from werewolf.tagger.tags import Tag, TagFile, save_tags


def games(tmp_path: Path, count: int = 2) -> Path:
    folder = tmp_path / "games"
    folder.mkdir()
    for n in range(count):
        log = base_log(
            talk((VILLAGER, f"g{n} one"), (WOLF_A, f"g{n} two"), (VILLAGER, f"g{n} three"))
        )
        (folder / f"{n + 1}-abc.json").write_bytes(log.to_json().encode("utf-8"))
    return folder


def typed(*answers: str) -> Callable[[str], str]:
    queue: Iterator[str] = iter(answers)
    return lambda prompt: next(queue)


def test_every_public_message_becomes_an_item_with_up_to_three_lines_of_context(
    tmp_path: Path,
) -> None:
    items = collect([games(tmp_path)])
    assert len(items) == 6
    third = next(i for i in items if i.line == "R1-3" and i.game == "1-abc")
    assert [c[2] for c in third.context] == ["g0 one", "g0 two"]
    assert third.text == "g0 three" and third.speaker == VILLAGER


def test_the_sample_is_reproducible_and_asks_for_no_more_than_exist(tmp_path: Path) -> None:
    items = collect([games(tmp_path)])
    first = [(i.game, i.line) for i in sample(items, 4, seed=1)]
    assert first == [(i.game, i.line) for i in sample(items, 4, seed=1)]
    assert len(set(first)) == 4
    assert first != [(i.game, i.line) for i in sample(items, 4, seed=2)] or len(items) < 5
    assert len(sample(items, 100, seed=1)) == 6


def test_a_label_is_saved_at_once_and_the_session_resumes_where_it_stopped(tmp_path: Path) -> None:
    items = sample(collect([games(tmp_path)]), 6, seed=1)
    store = tmp_path / "mine.jsonl"
    names = list(MOVE_NAMES)
    done = run_session(items, store, ask=typed("4", "", "s", "6,8", "", "q"), out=lambda s: None)
    assert done == 2
    saved = load_labels(store)
    assert len(saved) == 2
    assert any(label.moves == (names[3],) for label in saved.values())
    assert any(label.moves == (names[5], names[7]) for label in saved.values())
    # a second session skips what is labeled and asks about the rest, including the skipped one
    asked: list[str] = []

    def count(prompt: str) -> str:
        asked.append(prompt)
        return "q"

    run_session(items, store, ask=count, out=lambda s: None)
    assert len(asked) == 1  # it stops at the first message that is not labeled yet


def test_moves_can_be_typed_as_names_and_a_target_must_be_a_player(tmp_path: Path) -> None:
    items = sample(collect([games(tmp_path, 1)]), 1, seed=1)
    store = tmp_path / "mine.jsonl"
    run_session(items, store, ask=typed("probe", "Nobody", f"{WOLF_A}"), out=lambda s: None)
    (label,) = load_labels(store).values()
    assert label == Label(moves=("probe",), target=WOLF_A)


@pytest.mark.parametrize("bad", ["", "0", "12", "1,2,3", "shout", "4,4"])
def test_a_bad_move_entry_is_asked_again(tmp_path: Path, bad: str) -> None:
    items = sample(collect([games(tmp_path, 1)]), 1, seed=1)
    store = tmp_path / "mine.jsonl"
    shown: list[str] = []
    run_session(items, store, ask=typed(bad, "5", ""), out=shown.append)
    assert len(load_labels(store)) == 1
    assert any("one or two" in line or "not a move" in line for line in shown)


def tagged(folder: Path, moves_by_line: dict[str, tuple[str, ...]]) -> None:
    for log_path in folder.glob("*.json"):
        tags = [
            Tag(line=line, speaker=VILLAGER, round=1, moves=moves)
            for line, moves in moves_by_line.items()
        ]
        save_tags(log_path, TagFile(model="m", tags=tags))


def write_labels(path: Path, game: str, labels: dict[str, tuple[str, ...]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for line, moves in labels.items():
            f.write(
                json.dumps({"game": game, "line": line, "moves": list(moves), "target": ""}) + "\n"
            )


def test_accuracy_counts_agreement_per_move_by_hand(tmp_path: Path) -> None:
    folder = games(tmp_path, 1)
    tagged(folder, {"R1-1": ("probe",), "R1-2": ("accuse_bare",), "R1-3": ("hedge", "probe")})
    store = tmp_path / "mine.jsonl"
    write_labels(
        store,
        "1-abc",
        {"R1-1": ("probe",), "R1-2": ("accuse_reasoned",), "R1-3": ("hedge",)},
    )
    report = accuracy([folder], load_labels(store))
    assert report.messages == 3 and report.untagged == 0
    assert report.exact == 1  # only R1-1 has the same set of moves
    assert report.overlap == 2  # R1-1 and R1-3 share at least one move
    probe = report.moves["probe"]
    assert (probe.mine, probe.tagger, probe.both) == (1, 2, 1)
    hedge = report.moves["hedge"]
    assert (hedge.mine, hedge.tagger, hedge.both) == (1, 1, 1)
    bare = report.moves["accuse_bare"]
    assert (bare.mine, bare.tagger, bare.both) == (0, 1, 0)


def test_a_labeled_message_the_tagger_missed_counts_as_untagged_not_as_agreement(
    tmp_path: Path,
) -> None:
    folder = games(tmp_path, 1)
    tagged(folder, {"R1-1": ("probe",)})
    store = tmp_path / "mine.jsonl"
    write_labels(store, "1-abc", {"R1-1": ("probe",), "R1-2": ("probe",)})
    report = accuracy([folder], load_labels(store))
    assert report.messages == 1 and report.untagged == 1 and report.exact == 1


def test_the_report_text_names_each_move_and_gives_intervals(tmp_path: Path) -> None:
    folder = games(tmp_path, 1)
    tagged(folder, {"R1-1": ("probe",)})
    store = tmp_path / "mine.jsonl"
    write_labels(store, "1-abc", {"R1-1": ("probe",)})
    text = format_accuracy(accuracy([folder], load_labels(store)))
    assert "same moves: 100% (1/1" in text and "probe" in text and "recall" in text


def test_the_commands_label_and_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = games(tmp_path, 1)
    tagged(folder, {"R1-1": ("probe",), "R1-2": ("probe",), "R1-3": ("probe",)})
    store = tmp_path / "labels" / "mine.jsonl"
    answers = iter(["5", "", "5", "", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["label", str(folder), "--count", "3", "--seed", "1", "--file", str(store)]) == 0
    assert len(load_labels(store)) == 2
    capsys.readouterr()
    assert main(["accuracy", str(folder), "--file", str(store)]) == 0
    assert "same moves" in capsys.readouterr().out
    assert main(["accuracy", str(folder), "--file", str(tmp_path / "none.jsonl")]) == 1
