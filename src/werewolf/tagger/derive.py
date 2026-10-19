"""Labels worked out in code from the hidden roles: lies, fake claims, busing, and so on.

No model is involved. The tagger says what a message did; the game log says what was true.
"""

from collections.abc import Sequence

from werewolf.engine.events import SeerResult, VoteCast
from werewolf.engine.log import GameLog
from werewolf.engine.roles import Role
from werewolf.tagger.moves import ACCUSE_MOVES
from werewolf.tagger.tags import DerivedTag, Tag, line_key

POWER_ROLES = (Role.SEER.value, Role.DOCTOR.value)


def _claim_is_true(log: GameLog, tag: Tag, roles: dict[str, Role], role_said: str) -> bool | None:
    """True or false if the log can tell; None if the claim leaves out what is needed."""
    claim = tag.claimed
    assert claim is not None
    if "result_claim" in tag.moves:
        if claim.result not in ("wolf", "not_wolf") or not claim.checked:
            return None
        if roles[tag.speaker] is not Role.SEER:
            return False
        for event in log.events:
            if (
                isinstance(event, SeerResult)
                and event.target == claim.checked
                and event.round <= tag.round
            ):
                return (event.role is Role.WEREWOLF) == (claim.result == "wolf")
        return False  # the Seer never checked that player
    return roles[tag.speaker].value == role_said


def derive(log: GameLog, tags: Sequence[Tag]) -> list[DerivedTag]:
    roles = {p.name: p.role for p in log.players}
    wolves = [n for n, r in roles.items() if r is Role.WEREWOLF]
    partner = {w: o for w in wolves for o in wolves if o != w}
    first_claimant: dict[str, str] = {}
    out: list[DerivedTag] = []

    def add(tag: Tag, label: str, why: str, target: str | None = None) -> None:
        out.append(DerivedTag(
            round=tag.round, line=tag.line, speaker=tag.speaker, label=label, target=target, why=why
        ))  # fmt: skip

    for tag in sorted(tags, key=lambda t: line_key(t.line)):
        claim = tag.claimed
        if claim is not None and any(m in ("role_claim", "result_claim") for m in tag.moves):
            said = Role.SEER.value if "result_claim" in tag.moves else claim.role
            true = _claim_is_true(log, tag, roles, said)
            if true is False:
                add(
                    tag,
                    "lie",
                    f"claimed {said}; the speaker is {roles[tag.speaker].value}"
                    if "role_claim" in tag.moves
                    else "the claimed check does not match the log",
                )
            if said in POWER_ROLES:
                if roles[tag.speaker] is Role.WEREWOLF:
                    add(tag, "fake_claim", f"a wolf claimed {said}")
                if first_claimant.setdefault(said, tag.speaker) != tag.speaker:
                    add(tag, "counter_claim", f"{first_claimant[said]} already claimed {said}")
        accuses = any(m in ACCUSE_MOVES for m in tag.moves)
        if accuses and tag.target in roles and roles[tag.target] is Role.WEREWOLF:
            add(tag, "hit", f"{tag.target} is a wolf", tag.target)
        if tag.speaker in partner and tag.target == partner[tag.speaker]:
            if accuses:
                add(tag, "bus", "a wolf accused its partner", tag.target)
            if "vouch" in tag.moves:
                add(tag, "shield", "a wolf vouched for its partner", tag.target)

    for event in log.events:
        if isinstance(event, VoteCast) and event.target is not None:
            if partner.get(event.voter) == event.target:
                out.append(DerivedTag(
                    round=event.round, line=None, speaker=event.voter, label="bus",
                    target=event.target, why="a wolf voted for its partner",
                ))  # fmt: skip
    return out
