"""The tag command and show --tags, with a pretend model behind the real client."""

from pathlib import Path

import pytest
from test_derive import SEER, VILLAGER, WOLF_A, WOLF_B, base_log
from test_tagger import MODEL, PLAIN, Rig, talk

from werewolf import runtime
from werewolf.cli import main
from werewolf.engine.log import GameLog
from werewolf.llm.client import LLMClient
from werewolf.tagger.tags import load_tags, tags_path


def install(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build(model: str, max_spend: object, **kw: object) -> LLMClient:
        return rig.client

    monkeypatch.setattr(runtime, "build_client", fake_build)


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    rig = Rig(tmp_path / "rig")
    install(rig, monkeypatch)
    return rig


def games(tmp_path: Path, count: int = 3) -> Path:
    folder = tmp_path / "games"
    folder.mkdir()
    for n in range(count):
        log = base_log(talk((VILLAGER, f"game {n} hello"), (WOLF_A, "Why?")))
        (folder / f"{n + 1}-abc.json").write_bytes(log.to_json().encode("utf-8"))
    return folder


def tag(folder: Path, *extra: str) -> int:
    return main(["tag", str(folder), "--model", MODEL, "--max-spend", "1.00", *extra])


def test_a_folder_of_games_gets_one_tag_file_each_and_a_rerun_costs_nothing(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = games(tmp_path)
    assert tag(folder) == 0
    files = sorted(folder.glob("*.tags.json"))
    assert len(files) == 3 and len(rig.model.calls) == 6
    spent = rig.ledger.spent("openai")
    capsys.readouterr()
    assert tag(folder) == 0
    assert "already tagged" in capsys.readouterr().out
    assert len(rig.model.calls) == 6 and rig.ledger.spent("openai") == spent


def test_again_retags_but_the_cache_makes_it_free(rig: Rig, tmp_path: Path) -> None:
    folder = games(tmp_path, 1)
    tag(folder)
    spent = rig.ledger.spent("openai")
    assert tag(folder, "--again") == 0
    assert len(rig.model.calls) == 2 and rig.ledger.spent("openai") == spent


def test_the_tag_file_reads_back_and_a_tag_file_is_not_taken_for_a_game(
    rig: Rig, tmp_path: Path
) -> None:
    folder = games(tmp_path, 1)
    tag(folder)
    (game,) = [p for p in folder.glob("*.json") if not p.name.endswith(".tags.json")]
    saved = load_tags(game)
    assert saved is not None and saved.model == MODEL
    assert [t.line for t in saved.tags] == ["R1-1", "R1-2"]
    assert tags_path(game).exists()
    assert tag(folder, "--again") == 0 and len(list(folder.glob("*.tags.json"))) == 1


def test_show_tags_prints_moves_and_hides_the_labels_unless_private(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.model.by_line["R1-2"] = {**PLAIN, "move1": "accuse_bare", "target": WOLF_B}
    folder = games(tmp_path, 1)
    tag(folder)
    (game,) = [p for p in folder.glob("*.json") if not p.name.endswith(".tags.json")]
    capsys.readouterr()
    assert main(["show", str(game), "--tags"]) == 0
    public = capsys.readouterr().out
    assert "accuse_bare" in public and "hit" not in public.split("Tags by")[1]
    assert main(["show", str(game), "--tags", "--private"]) == 0
    assert "hit: " + WOLF_B in capsys.readouterr().out


def test_show_tags_with_no_tags_says_so(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = games(tmp_path, 1)
    (game,) = folder.glob("*.json")
    assert main(["show", str(game), "--tags"]) == 1
    assert "no tags yet" in capsys.readouterr().err


def test_a_cap_hit_stops_the_run_saves_no_half_file_and_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path / "rig", cap="0")
    install(rig, monkeypatch)
    folder = games(tmp_path, 2)
    assert tag(folder) == 1
    assert "STOPPED" in capsys.readouterr().out
    assert list(folder.glob("*.tags.json")) == [] and rig.model.calls == []


def test_a_paid_model_without_a_spending_limit_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = games(tmp_path, 1)
    assert main(["tag", str(folder), "--model", MODEL]) == 2
    assert "--max-spend" in capsys.readouterr().err


def test_an_unreadable_game_file_is_reported_and_the_rest_still_run(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = games(tmp_path, 1)
    (folder / "0-bad.json").write_text("{not json", encoding="utf-8")
    assert tag(folder) == 2
    assert "cannot read" in capsys.readouterr().err
    assert len(list(folder.glob("*.tags.json"))) == 1


def test_the_log_files_are_valid_games() -> None:
    assert GameLog.from_json(base_log(talk((SEER, "hi"))).to_json())
