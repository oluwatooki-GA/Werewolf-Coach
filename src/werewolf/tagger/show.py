"""A game's messages with the moves the tagger found and, in private mode, the derived labels."""

from collections import defaultdict

from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.tagger.derive import derive
from werewolf.tagger.tags import DerivedTag, TagFile


def render_tags(log: GameLog, tagfile: TagFile, private: bool = False) -> str:
    """Public mode shows only what the tagger saw. Private mode adds the labels that need the
    hidden roles (lie, fake_claim, counter_claim, bus, shield, hit), since they give roles away."""
    by_line = {t.line: t for t in tagfile.tags}
    labels: dict[str | None, list[DerivedTag]] = defaultdict(list)
    for item in derive(log, tagfile.tags) if private else []:
        labels[item.line].append(item)
    lines = [f"Tags by {tagfile.model}:"]
    for line, speech in numbered_speeches(log.events):
        lines.append(f"[{line}] {speech.speaker}: {speech.text}")
        tag = by_line.get(line)
        if tag is None:
            lines.append(f"    not tagged: {tagfile.untagged.get(line, 'no tag')}")
            continue
        parts = ["+".join(tag.moves)]
        if tag.target:
            parts.append(f"-> {tag.target}")
        if tag.claimed:
            claim = tag.claimed
            said = [f"role {claim.role}"] if claim.role else []
            said += [f"checked {claim.checked}: {claim.result}"] if claim.checked else []
            said += [f"vote of {claim.vote}"] if claim.vote else []
            parts.append("(" + ", ".join(said) + ")")
        if labels[line]:
            parts.append("[" + ", ".join(f"{d.label}: {d.why}" for d in labels[line]) + "]")
        lines.append("    " + " ".join(parts))
    for item in labels[None]:
        lines.append(f"[vote, round {item.round}] {item.speaker}: {item.label} ({item.why})")
    return "\n".join(lines)
