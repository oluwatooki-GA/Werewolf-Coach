"""Derived labels, worked out from the hidden roles on a game whose roles are known."""

import asyncio

from werewolf.agents.scripted import policy
from werewolf.engine.events import Event, SeerResult, VoteCast
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.tagger.derive import derive
from werewolf.tagger.tags import Claimed, Tag


def base_log(events: list[Event]) -> GameLog:
    players = new_game(1).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    agents = {p.name: policy(wolves) for p in players}
    log = to_log(asyncio.run(play_game(1, None, agents)))
    return log.model_copy(update={"events": events})


def names(role: Role) -> list[str]:
    return [p.name for p in new_game(1).players if p.role is role]


SEER = names(Role.SEER)[0]
DOCTOR = names(Role.DOCTOR)[0]
WOLF_A, WOLF_B = names(Role.WEREWOLF)
VILLAGER, OTHER = names(Role.VILLAGER)[:2]

CHECKED_WOLF = SeerResult(round=1, target=WOLF_A, role=Role.WEREWOLF, audience=(SEER,))
CHECKED_VILLAGER = SeerResult(round=1, target=VILLAGER, role=Role.VILLAGER, audience=(SEER,))


def tag(speaker: str, *moves: str, line: str = "R1-1", target: str | None = None,
        claimed: Claimed | None = None, round: int = 1) -> Tag:  # fmt: skip
    return Tag(line=line, speaker=speaker, round=round, moves=moves, target=target, claimed=claimed)


def result(who: str, checked: str, said: str, line: str = "R1-1") -> Tag:
    return tag(who, "result_claim", line=line, target=checked,
               claimed=Claimed(role="Seer", checked=checked, result=said))  # fmt: skip


def role(who: str, said: str, line: str = "R1-1") -> Tag:
    return tag(who, "role_claim", line=line, claimed=Claimed(role=said))


def labels(events: list[Event], *tags: Tag) -> list[tuple[str, str]]:
    return [(d.speaker, d.label) for d in derive(base_log(events), tags)]


def test_a_true_result_from_the_real_seer_is_not_a_lie() -> None:
    assert labels([CHECKED_WOLF], result(SEER, WOLF_A, "wolf")) == []
    assert labels([CHECKED_VILLAGER], result(SEER, VILLAGER, "not_wolf")) == []


def test_a_wrong_result_from_the_real_seer_is_a_lie() -> None:
    assert labels([CHECKED_WOLF], result(SEER, WOLF_A, "not_wolf")) == [(SEER, "lie")]


def test_a_result_about_someone_the_seer_never_checked_is_a_lie() -> None:
    assert labels([CHECKED_WOLF], result(SEER, OTHER, "wolf")) == [(SEER, "lie")]


def test_a_result_from_a_villager_is_a_lie_but_not_a_fake_claim() -> None:
    assert labels([CHECKED_WOLF], result(VILLAGER, WOLF_A, "wolf")) == [(VILLAGER, "lie")]


def test_a_wolf_claiming_seer_is_a_lie_and_a_fake_claim() -> None:
    assert labels([], role(WOLF_A, "Seer")) == [(WOLF_A, "lie"), (WOLF_A, "fake_claim")]


def test_a_wolf_claiming_villager_is_a_lie_but_not_a_fake_claim() -> None:
    assert labels([], role(WOLF_A, "Villager")) == [(WOLF_A, "lie")]


def test_true_claims_get_no_labels() -> None:
    assert labels([], role(DOCTOR, "Doctor")) == []
    assert labels([], role(VILLAGER, "Villager")) == []


def test_a_second_claimant_is_a_counter_claim_and_the_same_player_repeating_is_not() -> None:
    first = role(SEER, "Seer", "R1-1")
    again = role(SEER, "Seer", "R1-2")
    second = role(WOLF_A, "Seer", "R1-3")
    got = labels([], first, again, second)
    assert (WOLF_A, "counter_claim") in got
    assert (SEER, "counter_claim") not in got


def test_a_claim_without_the_needed_facts_is_left_alone() -> None:
    vague = tag(SEER, "result_claim", claimed=Claimed(role="Seer"))
    assert labels([CHECKED_WOLF], vague) == []


def test_a_wolf_accusing_its_partner_is_bus_and_a_hit() -> None:
    got = labels([], tag(WOLF_A, "accuse_bare", target=WOLF_B))
    assert got == [(WOLF_A, "hit"), (WOLF_A, "bus")]


def test_a_villager_accusing_a_wolf_is_a_hit_and_accusing_a_villager_is_nothing() -> None:
    assert labels([], tag(VILLAGER, "accuse_reasoned", target=WOLF_A)) == [(VILLAGER, "hit")]
    assert labels([], tag(VILLAGER, "accuse_reasoned", target=OTHER)) == []


def test_a_wolf_accusing_a_villager_is_nothing() -> None:
    assert labels([], tag(WOLF_A, "accuse_reasoned", target=VILLAGER)) == []


def test_a_wolf_vouching_for_its_partner_is_a_shield_and_for_a_villager_is_nothing() -> None:
    assert labels([], tag(WOLF_A, "vouch", target=WOLF_B)) == [(WOLF_A, "shield")]
    assert labels([], tag(WOLF_A, "vouch", target=VILLAGER)) == []
    assert labels([], tag(VILLAGER, "vouch", target=WOLF_B)) == []


def test_a_wolf_voting_for_its_partner_is_bus_without_a_line() -> None:
    vote = VoteCast(round=1, voter=WOLF_A, target=WOLF_B, reason="")
    (found,) = derive(base_log([vote]), [])
    assert (found.speaker, found.label, found.line) == (WOLF_A, "bus", None)
    other = VoteCast(round=1, voter=VILLAGER, target=WOLF_B, reason="")
    assert derive(base_log([other]), []) == []


def test_a_plain_message_gets_no_labels() -> None:
    assert labels([], tag(VILLAGER, "hedge"), tag(WOLF_A, "probe", target=OTHER)) == []
