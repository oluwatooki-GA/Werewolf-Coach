"""What the coach reads: the games a side lost, names taken out, counts it can trust."""

from coach_support import (
    SEER,
    VILLAGERS,
    WOLF_A,
    WOLF_B,
    Game,
    claim_tag,
    make_log,
    note_call,
    removed,
    speech,
    tag,
    tags_for,
    vote,
)

from werewolf.coach.evidence import build_evidence
from werewolf.engine.roles import Role, Team
from werewolf.tagger.tags import TagFile

V1, V2 = VILLAGERS[0], VILLAGERS[1]


def village_won(card: str | None = None) -> Game:
    """A game the wolves lost: wolf A speaks and is voted out in round 1."""
    events = [
        speech(1, WOLF_A, f"{V1}, why so quiet?"),
        speech(1, V1, f"{WOLF_A}, you push too fast."),
        vote(1, V1, WOLF_A, "pushed too fast"),
        vote(1, WOLF_B, V1),
        removed(1, WOLF_A),
    ]
    log = make_log(Team.VILLAGE, events, rounds=2, card=card)
    return log, tags_for(
        tag("R1-1", WOLF_A, 1, "probe", target=V1), tag("R1-2", V1, 1, "accuse_reasoned")
    )


def wolves_won(card: str | None = None) -> Game:
    events = [speech(1, WOLF_A, "Hello."), vote(1, WOLF_A, V1), removed(1, V1)]
    return make_log(Team.WOLVES, events, rounds=3, card=card), tags_for(
        tag("R1-1", WOLF_A, 1, "hedge")
    )


def test_only_games_the_side_lost_are_included() -> None:
    games = [village_won(), wolves_won(), village_won()]
    wolf = build_evidence(games, "wolf")
    assert (wolf.games, wolf.lost, wolf.used) == (3, 2, 2)
    villager = build_evidence(games, "villager")
    assert (villager.games, villager.lost, villager.used) == (3, 1, 1)  # the villagers lost one


def test_real_names_never_reach_the_coach_and_roles_do() -> None:
    from werewolf.engine.state import DEFAULT_NAMES

    text = build_evidence([village_won()], "wolf").text
    for name in DEFAULT_NAMES:
        assert name not in text.replace("Wolf", "").replace("Villager", ""), name
    assert "Wolf A" in text and "Villager 1" in text


def test_the_digest_shows_the_sides_messages_with_moves_and_derived_labels() -> None:
    events = [speech(1, WOLF_A, "I am the Seer."), vote(1, V1, WOLF_A), removed(1, WOLF_A)]
    games = [(make_log(Team.VILLAGE, events), tags_for(claim_tag("R1-1", WOLF_A, "Seer")))]
    text = build_evidence(games, "wolf").text
    assert "role_claim" in text and "fake_claim" in text and "lie" in text


def test_the_side_notes_are_included_and_the_opponents_notes_are_not() -> None:
    calls = [
        note_call(1, WOLF_A, "my plan is to blame the quiet one"),
        note_call(1, V1, "wolf a is lying"),
    ]
    events = [speech(1, WOLF_A, "hi"), removed(1, WOLF_A)]
    games = [(make_log(Team.VILLAGE, events, calls=calls), tags_for())]
    text = build_evidence(games, "wolf").text
    assert "blame the quiet one" in text and "wolf a is lying" not in text


def test_aggregate_counts_equal_hand_worked_values() -> None:
    # four games, all lost by the wolves. Wolf A accuses in round 1 in games 1, 2 and 3 and is
    # removed by the end of round 2 in games 1 and 2; in game 4 it does not accuse and survives.
    def game(accuses: bool, removed_round: int | None) -> Game:
        line = [speech(1, WOLF_A, "Odd.")] if accuses else [speech(1, V2, "Hello.")]
        events: list[object] = [*line]
        if removed_round:
            events.append(removed(removed_round, WOLF_A))
        moves = tags_for(tag("R1-1", WOLF_A, 1, "accuse_reasoned")) if accuses else tags_for()
        return make_log(Team.VILLAGE, events, rounds=3), moves

    games = [game(True, 1), game(True, 2), game(True, None), game(False, None)]
    text = build_evidence(games, "wolf").text
    assert "accused in round 1: 3 of 8" in text  # 3 accusing seats out of 8 wolf-seat-games
    assert "voted out by the end of round 2: 2 of 3" in text
    assert "did not accuse in round 1: voted out by the end of round 2: 0 of 5" in text


def test_a_set_bigger_than_the_limit_is_cut_and_says_how_many_were_left_out() -> None:
    games = [village_won() for _ in range(6)]
    one = len(build_evidence(games[:1], "wolf").text)
    cut = build_evidence(games, "wolf", max_chars=one * 3)
    assert 1 <= cut.used < 6 and cut.left_out == 6 - cut.used
    assert f"{cut.left_out} more lost games were left out" in cut.text


def test_a_side_that_won_everything_has_nothing_to_learn_from() -> None:
    result = build_evidence([wolves_won(), wolves_won()], "wolf")
    assert result.empty and result.used == 0
    assert "nothing to learn from" in result.text


def test_only_games_that_played_the_named_card_are_used() -> None:
    games = [village_won("wolf.accuse_early@2"), village_won("wolf.lie_low@1")]
    result = build_evidence(games, "wolf", card_id="wolf.accuse_early")
    assert (result.games, result.used) == (1, 1)


def test_untagged_games_still_work() -> None:
    log, _ = village_won()
    result = build_evidence([(log, None)], "wolf")
    assert result.used == 1 and "not tagged" in result.text


def test_a_villager_digest_describes_the_village_side_and_a_role_label_for_the_seer() -> None:
    events = [speech(1, V1, f"{SEER}, who did you check?"), vote(1, V1, WOLF_A), removed(1, V1)]
    games = [(make_log(Team.WOLVES, events, side_role=Role.VILLAGER), TagFile(model="m", tags=[]))]
    text = build_evidence(games, "villager").text
    assert "Seer" in text and SEER not in text.replace("Seer", "")
