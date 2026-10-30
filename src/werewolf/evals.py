"""The eval check: replay a fixed set of recorded games with no model and hold three numbers.

* rejected answers: recorded answers the current rules turn away (a looser or stricter check, a
  changed answer shape, a new question the game did not ask when it was recorded),
* prompt leaks: private text found in a prompt the current code builds for those games,
* adherence: how often a card's players make the moves the card expects.

Replay is deterministic, so any change in the numbers comes from the code or the cards, never from
chance. A change that makes a number worse fails; the baseline file is rewritten on purpose when a
change is meant to move them.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from werewolf.audit import find_leaks
from werewolf.engine.log import GameLog, replay
from werewolf.promptview import rebuild
from werewolf.tagger.adherence import adherence
from werewolf.tagger.tags import TagFile, load_tags

ADHERENCE_TOLERANCE = 0.05  # a card may be followed this much less (in share) before it fails


@dataclass(frozen=True)
class Measures:
    games: int
    responses: int  # recorded answers, counting a second try as another answer
    rejected: int  # of those, the ones the current rules turned away
    replay_errors: int  # games that could not be replayed at all
    leaks: int
    adherence: dict[str, tuple[int, int]]  # card -> (messages with an expected move, messages)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=1, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Measures":
        data: dict[str, Any] = json.loads(text)
        data["adherence"] = {card: (int(a), int(n)) for card, (a, n) in data["adherence"].items()}
        return cls(**data)


def measure(directory: Path) -> Measures:
    paths = sorted(p for p in directory.glob("*.json") if not p.name.endswith(".tags.json"))
    responses = rejected = errors = leaks = 0
    tagged: list[tuple[GameLog, TagFile]] = []
    for path in paths:
        log = GameLog.from_json(path.read_text(encoding="utf-8"))
        try:
            again = replay(log)
            prompts = [(item.player, item.messages) for item in rebuild(log)]
            found = len(find_leaks(log, prompts))
        except Exception:  # a game the current code cannot replay is a result, not a crash
            errors += 1
            continue
        responses += again.stats.responses
        rejected += again.stats.rejected
        leaks += found
        tags = load_tags(path)
        if tags is not None:
            tagged.append((log, tags))
    stats = adherence(tagged)
    return Measures(
        games=len(paths),
        responses=responses,
        rejected=rejected,
        replay_errors=errors,
        leaks=leaks,
        adherence={card: (s.adhering, s.messages) for card, s in sorted(stats.items())},
    )


def _share(k: int, n: int) -> float:
    return k / n if n else 0.0


def compare(before: Measures, after: Measures) -> list[str]:
    """What got worse, in plain words. Nothing means the change is fine."""
    problems = []
    if after.games != before.games:
        problems.append(
            f"The recorded games changed ({before.games} before, {after.games} now): "
            "write a new baseline with --write-baseline."
        )
    if after.replay_errors > before.replay_errors:
        problems.append(
            f"{after.replay_errors} recorded game(s) no longer replay (was {before.replay_errors})."
        )
    if after.rejected * before.responses > before.rejected * after.responses:
        problems.append(
            "More recorded answers are rejected: "
            f"{before.rejected} of {before.responses} before, "
            f"{after.rejected} of {after.responses} now."
        )
    if after.leaks > before.leaks:
        problems.append(f"Prompts leak private text: {after.leaks} now, {before.leaks} before.")
    for card, (k, n) in sorted(before.adherence.items()):
        if card not in after.adherence:
            problems.append(f"{card} is no longer measured.")
            continue
        was, now = _share(k, n), _share(*after.adherence[card])
        if was - now > ADHERENCE_TOLERANCE + 1e-9:
            problems.append(f"{card} is followed less: {was:.0%} before, {now:.0%} now.")
    return problems


def _way(before: float, after: float) -> str:
    """For a number where less is better."""
    return "same" if before == after else "better" if after < before else "worse"


def _count(k: int, n: int) -> str:
    return f"{k} of {n} ({_share(k, n):.1%})"


def table(before: Measures, after: Measures) -> str:
    """Before beside after, as a markdown table."""
    rows = [
        (
            "Rejected answers",
            _count(before.rejected, before.responses),
            _count(after.rejected, after.responses),
            _way(
                _share(before.rejected, before.responses), _share(after.rejected, after.responses)
            ),
        ),
        (
            "Games that no longer replay",
            str(before.replay_errors),
            str(after.replay_errors),
            _way(before.replay_errors, after.replay_errors),
        ),
        ("Prompt leaks", str(before.leaks), str(after.leaks), _way(before.leaks, after.leaks)),
    ]
    for card in sorted(set(before.adherence) | set(after.adherence)):
        was, now = before.adherence.get(card), after.adherence.get(card)
        if was is None or now is None:
            way = "not comparable"
        elif _share(*now) == _share(*was):
            way = "same"
        else:
            way = "higher" if _share(*now) > _share(*was) else "lower"
        rows.append(
            (
                f"Follows {card}",
                _count(*was) if was else "not measured",
                _count(*now) if now else "not measured",
                way,
            )
        )
    lines = ["| Measure | Before | After | |", "| --- | --- | --- | --- |"]
    lines += [f"| {name} | {was} | {now} | {way} |" for name, was, now, way in rows]
    return "\n".join(lines)
