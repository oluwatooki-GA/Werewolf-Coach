"""The replay: a finished game as numbered lines, each beside the speaker's private subtext."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coach"))

from api_support import build  # noqa: E402
from coach_support import (  # noqa: E402
    SEER,
    VILLAGERS,
    WOLF_A,
    WOLF_B,
    claim_tag,
    make_log,
    removed,
    speech,
    tag,
    tags_for,
    vote,
)
from fastapi.testclient import TestClient  # noqa: E402

from werewolf.api.app import create_app  # noqa: E402
from werewolf.api.deps import ApiSettings  # noqa: E402
from werewolf.api.replay import build_replay  # noqa: E402
from werewolf.engine.events import (  # noqa: E402
    Death,
    GameOver,
    Listening,
    NightSummary,
    WolfChat,
)
from werewolf.engine.roles import Team  # noqa: E402
from werewolf.engine.state import CallRecord  # noqa: E402

V1, V2 = VILLAGERS[0], VILLAGERS[1]


def bid_call(round_: int, player: str, message: str, note: str, bid: int = 2) -> CallRecord:
    answer = {
        "bid": bid, "message": message, "intent": "accuse", "target": V1, "note": note,
        "beliefs": [{"player": V1, "suspicion": 0.7, "reason": "quiet"}], "cites": [],
    }  # fmt: skip
    return CallRecord(
        round=round_, player=player, task={"kind": "bid", "max_bid": 4},
        responses=[json.dumps(answer)], errors=[], rejected=0, failed=False,
    )  # fmt: skip


def vote_call(round_: int, player: str, note: str) -> CallRecord:
    answer = {"target": WOLF_A, "reason": "r", "note": note, "beliefs": []}
    return CallRecord(
        round=round_, player=player, task={"kind": "vote", "options": []},
        responses=[json.dumps(answer)], errors=[], rejected=0, failed=False,
    )  # fmt: skip


def game():  # type: ignore[no-untyped-def]
    events = [
        WolfChat(round=1, speaker=WOLF_A, text="Take Gus.", audience=(WOLF_A, WOLF_B)),
        NightSummary(round=1, kill=V2, protect=None, check=None, saved=False),
        Death(round=1, player=V2),
        speech(1, WOLF_A, "I was asleep all night."),
        speech(1, V1, "Nobody sleeps that well."),
        speech(1, WOLF_A, "I claim Seer."),
        Listening(round=1, player=WOLF_B),
        vote(1, V1, WOLF_A, "pushed hard"),
        removed(1, WOLF_A),
        GameOver(round=1, winner=Team.VILLAGE),
    ]
    calls = [
        bid_call(1, WOLF_A, "I claim Seer.", "second plan: fake Seer", bid=3),
        bid_call(
            1, WOLF_A, "I was asleep all night.", "first plan: deny"
        ),  # asked in another order
        bid_call(1, V1, "Nobody sleeps that well.", "suspicious"),
        vote_call(1, V1, "wolves lie"),
    ]
    tags = tags_for(
        tag("R1-1", WOLF_A, 1, "self_defend"),
        claim_tag("R1-3", WOLF_A, "Seer"),
    )
    return make_log(Team.VILLAGE, events, rounds=1, calls=calls), tags


def lines(replay):  # type: ignore[no-untyped-def]
    return [e for e in replay.entries if e.kind == "line"]


def test_lines_are_numbered_the_way_the_game_cites_them_and_know_their_speaker() -> None:
    log, tags = game()
    replay = build_replay("g1", log, tags)
    assert [(line.ref, line.speaker) for line in lines(replay)] == [
        ("R1-1", WOLF_A), ("R1-2", V1), ("R1-3", WOLF_A),
    ]  # fmt: skip
    first = lines(replay)[0]
    assert first.role == "Werewolf" and first.team == "Wolves" and first.paid == 1


def test_a_private_note_goes_with_the_line_it_wrote_not_the_order_it_was_asked() -> None:
    log, tags = game()
    one, two, three = lines(build_replay("g1", log, tags))
    assert one.subtext and one.subtext.note == "first plan: deny"
    assert three.subtext and three.subtext.note == "second plan: fake Seer"
    assert three.subtext.bid == 3 and three.subtext.intent == "accuse"
    assert two.subtext and two.subtext.beliefs[0].player == V1
    assert two.subtext.beliefs[0].suspicion == pytest.approx(0.7)


def test_a_line_with_no_matching_call_has_no_subtext() -> None:
    log, _ = game()
    quiet = log.model_copy(update={"calls": []})
    assert all(line.subtext is None for line in lines(build_replay("g1", quiet, None)))


def test_tags_and_derived_labels_sit_on_the_line_they_describe() -> None:
    log, tags = game()
    one, _, three = lines(build_replay("g1", log, tags))
    assert one.moves == ["self_defend"]
    assert three.claim and three.claim.role == "Seer"
    assert {mark.label for mark in three.marks} >= {"lie", "fake_claim"}
    assert all(mark.why for mark in three.marks)


def test_the_story_between_the_lines_is_kept_in_order() -> None:
    log, tags = game()
    kinds = [e.kind for e in build_replay("g1", log, tags).entries]
    assert kinds == [
        "wolf_chat", "night", "direction", "line", "line", "line", "direction", "vote",
        "direction", "direction",
    ]  # fmt: skip


def test_private_entries_are_marked_so_the_page_can_seal_them() -> None:
    log, tags = game()
    entries = build_replay("g1", log, tags).entries
    private = {e.kind for e in entries if e.private}
    assert private == {"wolf_chat", "night"}
    assert not any(e.private for e in entries if e.kind in ("line", "direction"))


def test_the_replay_names_every_player_with_role_team_and_card() -> None:
    log, tags = game()
    replay = build_replay("g1", log, tags)
    roles = {p.name: (p.role, p.team) for p in replay.players}
    assert roles[SEER] == ("Seer", "Village") and roles[WOLF_B] == ("Werewolf", "Wolves")
    assert replay.winner == "Village" and replay.rounds == 1 and replay.tagged is True
    assert build_replay("g1", log, None).tagged is False


def test_the_replay_endpoint_returns_it_and_404s_for_an_unknown_game(tmp_path: Path) -> None:
    log, tags = game()
    engine = build(tmp_path, [log], tagged=(log.seed,))
    client = TestClient(create_app(engine, ApiSettings()))
    listed = client.get("/games").json()["games"]
    body = client.get(f"/games/{listed[0]['id']}/replay").json()
    assert body["winner"] == "Village" and body["entries"][0]["kind"] == "wolf_chat"
    assert client.get("/games/nope/replay").status_code == 404


def test_featured_picks_the_fake_claim_with_a_private_note_and_says_which_line(
    tmp_path: Path,
) -> None:
    log, _ = game()
    plain = build(tmp_path / "plain", [log], tagged=(log.seed,))
    assert TestClient(create_app(plain, ApiSettings())).get("/featured").status_code == 404
    claim = tags_for(claim_tag("R1-3", WOLF_A, "Seer"))
    engine = build(tmp_path / "claim", [log], tagged=(log.seed,), tagfile=claim)
    client = TestClient(create_app(engine, ApiSettings()))
    body = client.get("/featured").json()
    assert body["focus"] == "R1-3"
    assert client.get(f"/games/{body['game_id']}/replay").status_code == 200


def test_beliefs_are_read_in_the_form_real_games_store_them() -> None:
    """Real model answers keep beliefs as {player: {suspicion, reason}}, not a list."""
    log, tags = game()
    answer = {
        "bid": 2, "message": "Nobody sleeps that well.", "intent": "ask", "target": WOLF_A,
        "note": "suspicious",
        "beliefs": {WOLF_A: {"suspicion": 0.8, "reason": "lied"}, V2: {"suspicion": 0.1}},
    }  # fmt: skip
    call = CallRecord(
        round=1, player=V1, task={"kind": "bid", "max_bid": 4}, responses=[json.dumps(answer)],
        errors=[], rejected=0, failed=False,
    )  # fmt: skip
    other = log.model_copy(update={"calls": [call]})
    said = lines(build_replay("g1", other, tags))[1]
    assert said.subtext is not None
    beliefs = {b.player: (b.suspicion, b.reason) for b in said.subtext.beliefs}
    assert beliefs == {WOLF_A: (0.8, "lied"), V2: (0.1, "")}
