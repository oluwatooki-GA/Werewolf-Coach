import pytest
from test_day_tokens import bidders, names, play_day, say, speeches

from werewolf.engine.actions import BidAction
from werewolf.engine.events import (
    Cite,
    Death,
    NightSummary,
    NoDeath,
    NoRemoval,
    Removal,
    SeerResult,
    Speech,
    VoteCast,
    WolfChat,
)
from werewolf.engine.record import check_cites, claimed_roles, numbered_speeches, round_record
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game


def said(round_: int, speaker: str, text: str = "hi", **kw: object) -> Speech:
    return Speech.model_validate(
        {"round": round_, "speaker": speaker, "text": text, "paid": 1, **kw}
    )


def test_public_messages_are_numbered_from_one_in_each_round() -> None:
    events = [said(1, "Bo", "a"), said(1, "Cy", "b"), said(2, "Bo", "c")]
    found = [(line, s.text) for line, s in numbered_speeches(events)]
    assert found == [("R1-1", "a"), ("R1-2", "b"), ("R2-1", "c")]


def test_a_private_message_takes_no_number() -> None:
    private = said(1, "Bo", "secret", audience=("Bo",))
    events = [said(1, "Bo", "a"), private, said(1, "Cy", "b")]
    assert [line for line, _ in numbered_speeches(events)] == ["R1-1", "R1-2"]


def test_a_cite_is_real_only_when_the_line_exists_and_the_speaker_matches() -> None:
    events = [said(1, "Bo"), said(1, "Cy")]
    cites = [
        Cite(line="R1-1", speaker="Bo"),  # real
        Cite(line="R1-2", speaker="Bo"),  # a line, but Cy wrote it
        Cite(line="R9-1", speaker="Bo"),  # no such line
        Cite(line="nonsense", speaker="Bo"),
    ]
    _, invented = check_cites(cites, events)
    assert invented == ("R1-2", "R9-1", "NONSENSE")


def test_cites_are_tidied_before_they_are_checked() -> None:
    events = [said(1, "Bo")]
    cites = [
        Cite(line=" [r1-1] ", speaker="Bo "),
        Cite(line="R1-1", speaker="Bo"),  # the same cite again
    ]
    tidy, invented = check_cites(cites, events)
    assert tidy == (Cite(line="R1-1", speaker="Bo"),) and invented == ()


def test_a_line_that_comes_later_is_not_yet_real() -> None:
    assert check_cites([Cite(line="R1-2", speaker="Cy")], [said(1, "Bo")])[1] == ("R1-2",)


@pytest.mark.parametrize(
    ("speaker", "text", "roles"),
    [
        ("Di", "Di here. I am the Doctor, so I will not say more.", [Role.DOCTOR]),
        ("Hal", "Hal here, plain villager. Eve's death tells us little.", [Role.VILLAGER]),
        ("Cy", "I am Cy, a plain villager. I will not accuse anyone.", [Role.VILLAGER]),
        ("Eve", "I’m the Seer and I checked Bo.", [Role.SEER]),
        ("Ada", "I am the one asking the questions here.", []),
        ("Gus", "Di, you say you are the Doctor. Prove it.", []),
        ("Bo", "I am not the Seer, and I am not hiding.", []),
        ("Bo", "If I am the wolf, vote me out.", []),
        ("Fay", "Who here will claim Seer?", []),
        ("Fay", "I am the Seer, honest. I am the Seer.", [Role.SEER]),
    ],
)
def test_a_role_claim_is_read_only_from_plain_first_person_words(
    speaker: str, text: str, roles: list[Role]
) -> None:
    assert claimed_roles(speaker, text) == roles


def test_the_round_record_states_deaths_claims_votes_and_the_removal() -> None:
    events = [
        NightSummary(round=1, kill="Eve", protect=None, check=None, saved=False, audience=()),
        SeerResult(round=1, target="Fay", role=Role.VILLAGER, audience=("Eve",)),
        WolfChat(round=1, speaker="Bo", text="I am the Seer lol", audience=("Bo", "Gus")),
        Death(round=1, player="Eve"),
        said(1, "Ada", "Nothing to say."),
        said(1, "Di", "I am the Doctor."),
        VoteCast(round=1, voter="Fay", target="Di", reason="dodged"),
        VoteCast(round=1, voter="Di", target="Fay", reason="pushy"),
        VoteCast(round=1, voter="Bo", target="Di", reason="dodged"),
        VoteCast(round=1, voter="Cy", target=None, reason=""),
        Removal(round=1, player="Di"),
        said(2, "Bo", "I am the Seer."),  # another round: not in round 1's record
    ]
    assert round_record(events, 1) == (
        "Round 1: died in the night: Eve; claimed a role: Di Doctor (R1-2); "
        "votes: Di 2 (Fay, Bo); Fay 1 (Di); abstained: Cy; removed by the vote: Di."
    )


def test_the_round_record_says_when_nothing_happened() -> None:
    events = [NoDeath(round=2), NoRemoval(round=2)]
    assert round_record(events, 2) == (
        "Round 2: nobody died in the night; nobody was removed by the vote."
    )
    assert round_record([], 3) == "Round 3: nothing."


def test_a_posted_message_carries_its_cites_and_the_invented_ones() -> None:
    state = new_game(seed=1)
    a, b = names(state)[:2]
    good, bad = Cite(line="R1-1", speaker=a), Cite(line="R1-1", speaker=b)
    script = {
        a: [say(1, "first"), BidAction(bid=0)],
        b: [BidAction(bid=0), say(1, "I quote you", cites=(good, bad))],
    }
    play_day(state, bidders(state, script))
    first, second = speeches(state)
    assert first.cites == () and first.invented == ()
    assert second.cites == (good, bad) and second.invented == ("R1-1",)


def test_a_wrong_cite_never_rejects_the_message() -> None:
    state = new_game(seed=1)
    a = names(state)[0]
    wrong = Cite(line="R5-5", speaker="Nobody")
    play_day(state, bidders(state, {a: [say(1, "hello", cites=(wrong,))]}))
    (only,) = speeches(state)
    assert only.text == "hello" and only.invented == ("R5-5",)


def test_a_log_without_cites_keeps_its_old_shape() -> None:
    plain = said(1, "Bo").model_dump(mode="json")
    assert "cites" not in plain and "invented" not in plain
    cited = said(1, "Bo", cites=(Cite(line="R1-1", speaker="Cy"),), invented=("R1-1",))
    dumped = cited.model_dump(mode="json")
    assert dumped["cites"] == [{"line": "R1-1", "speaker": "Cy"}]
    assert dumped["invented"] == ["R1-1"]
    assert Speech.model_validate(dumped) == cited
