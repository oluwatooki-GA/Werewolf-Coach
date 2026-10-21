"""What a tag looks like on disk, and the file that holds a game's tags beside its log."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

TAG_SUFFIX = ".tags.json"


class Claimed(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str  # the role the speaker says it has: Seer, Doctor, Villager or Werewolf
    checked: str = ""  # who the speaker says it checked ("" if nobody)
    result: str = ""  # "wolf" or "not_wolf" ("" if no result was claimed)
    vote: str = ""  # the vote the message points at, as a player name ("" if none)


class Tag(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: str  # such as "R2-4"
    speaker: str
    round: int
    moves: tuple[str, ...]  # one or two moves from tagger.moves
    target: str | None = None
    claimed: Claimed | None = None


class DerivedTag(BaseModel):
    """A label the engine adds from the hidden roles. The tagger never sees these."""

    model_config = ConfigDict(frozen=True)

    round: int
    line: str | None  # None for a vote
    speaker: str
    label: str  # lie, fake_claim, counter_claim, bus, shield, hit
    target: str | None = None
    why: str


class TagFile(BaseModel):
    version: int = 1
    model: str  # the tagger model
    tags: list[Tag]
    untagged: dict[str, str] = {}  # line -> why it could not be tagged


def tags_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.stem + TAG_SUFFIX)


def load_tags(log_path: Path) -> TagFile | None:
    path = tags_path(log_path)
    if not path.exists():
        return None
    return TagFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_tags(log_path: Path, tagfile: TagFile) -> Path:
    path = tags_path(log_path)
    path.write_bytes((tagfile.model_dump_json(indent=1) + "\n").encode("utf-8"))
    return path


def game_files(paths: list[str]) -> list[Path]:
    """Game logs among the given files and folders (tag files are not games)."""
    found: list[Path] = []
    for item in paths:
        path = Path(item)
        files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
        found += [f for f in files if not f.name.endswith(TAG_SUFFIX)]
    return found


def line_key(line: str) -> tuple[int, int]:
    """'R2-4' sorts as (2, 4)."""
    left, _, right = line.strip("R").partition("-")
    return (int(left), int(right)) if left.isdigit() and right.isdigit() else (0, 0)
