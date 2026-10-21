"""Labeling messages by hand, and scoring the tagger against those labels.

You see a message with the three before it and type its moves, without seeing what the tagger
said. Each answer is saved to a file at once, so you can stop and come back. `accuracy` then
compares your moves with the tagger's, move by move.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from pydantic import BaseModel, ConfigDict

from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.tagger.adherence import wilson
from werewolf.tagger.moves import MOVE_NAMES
from werewolf.tagger.tags import game_files, line_key, load_tags

CONTEXT_LINES = 3
LABEL_FILE = Path("data/labels/mine.jsonl")


class Label(BaseModel):
    model_config = ConfigDict(frozen=True)

    moves: tuple[str, ...]
    target: str = ""


@dataclass(frozen=True)
class Item:
    game: str  # the log file's name without .json
    line: str
    speaker: str
    text: str
    players: tuple[str, ...]
    context: tuple[tuple[str, str, str], ...]  # (line, speaker, text) of up to three earlier lines


def collect(paths: Sequence[str | Path]) -> list[Item]:
    """Every public message in the given game logs."""
    items: list[Item] = []
    for path in game_files([str(p) for p in paths]):
        log = GameLog.from_json(path.read_text(encoding="utf-8"))
        speeches = numbered_speeches(log.events)
        players = tuple(p.name for p in log.players)
        for index, (line, speech) in enumerate(speeches):
            before = speeches[max(0, index - CONTEXT_LINES) : index]
            items.append(
                Item(
                    game=path.stem,
                    line=line,
                    speaker=speech.speaker,
                    text=speech.text,
                    players=players,
                    context=tuple((ln, s.speaker, s.text) for ln, s in before),
                )
            )
    return items


def sample(items: Sequence[Item], count: int, seed: int) -> list[Item]:
    """A reproducible random choice of messages, in a random but fixed order."""
    ordered = sorted(items, key=lambda i: (i.game, line_key(i.line)))
    return Random(seed).sample(ordered, min(count, len(ordered)))


def load_labels(path: Path) -> dict[tuple[str, str], Label]:
    if not path.exists():
        return {}
    found: dict[tuple[str, str], Label] = {}
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip():
            row = json.loads(text)
            found[(row["game"], row["line"])] = Label(
                moves=tuple(row["moves"]), target=row["target"]
            )
    return found


def save_label(path: Path, item: Item, label: Label) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"game": item.game, "line": item.line, "moves": list(label.moves), "target": label.target}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _parse_moves(text: str) -> tuple[tuple[str, ...] | None, str]:
    """(moves, "") or (None, why not). Numbers from the list or move names, one or two."""
    parts = [p for p in text.replace(",", " ").split() if p]
    moves: list[str] = []
    for part in parts:
        if part.isdigit() and 1 <= int(part) <= len(MOVE_NAMES):
            moves.append(MOVE_NAMES[int(part) - 1])
        elif part in MOVE_NAMES:
            moves.append(part)
        else:
            return None, f"'{part}' is not a move"
    if not 1 <= len(moves) <= 2 or len(set(moves)) != len(moves):
        return None, "type one or two different moves"
    return tuple(moves), ""


def _legend() -> str:
    return "  ".join(f"{n}={name}" for n, name in enumerate(MOVE_NAMES, start=1))


def run_session(
    items: Sequence[Item],
    store: Path,
    ask: Callable[[str], str],
    out: Callable[[str], None],
) -> int:
    """Ask about each message that has no label yet. 's' skips, 'q' stops. Returns new labels."""
    done = load_labels(store)
    new = 0
    todo = [i for i in items if (i.game, i.line) not in done]
    out(f"{len(done)} labeled, {len(todo)} to go.  Moves: {_legend()}")
    for item in todo:
        out("")
        for line, speaker, text in item.context:
            out(f"   [{line}] {speaker}: {text}")
        out(f">>>[{item.line}] {item.speaker}: {item.text}")
        label: Label | None = None
        while label is None:
            answer = ask("moves (one or two numbers or names, s skip, q quit): ").strip()
            if answer == "q":
                return new
            if answer == "s":
                break
            moves, why = _parse_moves(answer)
            if moves is None:
                out(why if why else "type one or two moves")
                continue
            while True:
                target = ask("target (a player's name, or Enter for none): ").strip()
                if not target or target in item.players:
                    break
                out(f"{target} is not a player here")
            label = Label(moves=moves, target=target)
        if label is not None:
            save_label(store, item, label)
            new += 1
    return new


@dataclass
class MoveStats:
    mine: int = 0  # messages where you used the move
    tagger: int = 0  # messages where the tagger used it
    both: int = 0


@dataclass
class Accuracy:
    messages: int = 0  # labeled messages the tagger also has a tag for
    untagged: int = 0  # labeled messages the tagger could not tag
    exact: int = 0  # the same set of moves
    overlap: int = 0  # at least one move in common
    models: set[str] = field(default_factory=set)
    moves: dict[str, MoveStats] = field(default_factory=dict)


def accuracy(paths: Sequence[str | Path], labels: dict[tuple[str, str], Label]) -> Accuracy:
    report = Accuracy(moves={name: MoveStats() for name in MOVE_NAMES})
    for path in game_files([str(p) for p in paths]):
        tagfile = load_tags(path)
        if tagfile is None:
            continue
        report.models.add(tagfile.model)
        by_line = {t.line: t for t in tagfile.tags}
        for (game, line), label in labels.items():
            if game != path.stem:
                continue
            tag = by_line.get(line)
            if tag is None:
                report.untagged += 1
                continue
            report.messages += 1
            mine, theirs = set(label.moves), set(tag.moves)
            report.exact += mine == theirs
            report.overlap += bool(mine & theirs)
            for name in MOVE_NAMES:
                stats = report.moves[name]
                stats.mine += name in mine
                stats.tagger += name in theirs
                stats.both += name in mine and name in theirs
    return report


def _rate(k: int, n: int) -> str:
    if n == 0:
        return "no data"
    low, high = wilson(k, n)
    return f"{100 * k / n:.0f}% ({k}/{n}, 95% {100 * low:.0f}-{100 * high:.0f}%)"


def format_accuracy(report: Accuracy) -> str:
    models = ", ".join(sorted(report.models)) or "no tagger"
    lines = [
        f"tagger {models} against your labels: {report.messages} messages"
        + (
            f", {report.untagged} you labeled that the tagger could not tag"
            if report.untagged
            else ""
        ),
        f"same moves: {_rate(report.exact, report.messages)}",
        f"at least one move in common: {_rate(report.overlap, report.messages)}",
        "",
        f"{'move':16} {'you':>4} {'tagger':>6} {'both':>5}  "
        "recall (of yours)     precision (of its)",
    ]
    for name in MOVE_NAMES:
        s = report.moves[name]
        if s.mine or s.tagger:
            lines.append(
                f"{name:16} {s.mine:>4} {s.tagger:>6} {s.both:>5}  "
                f"{_rate(s.both, s.mine):21} {_rate(s.both, s.tagger)}"
            )
    return "\n".join(lines)
