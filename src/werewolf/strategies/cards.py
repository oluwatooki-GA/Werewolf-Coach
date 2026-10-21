"""Strategy cards: short YAML files in cards/, loaded by id, checked before any game uses them."""

import re
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf.engine.roles import Role
from werewolf.engine.state import DEFAULT_NAMES
from werewolf.tagger.moves import MOVE_NAMES

CARDS_DIR = Path("cards")
MAX_WORDS = 80
ID_PREFIX = {
    Role.WEREWOLF: "wolf",
    Role.VILLAGER: "villager",
    Role.SEER: "seer",
    Role.DOCTOR: "doctor",
}
ROLE_FOR_PREFIX = {prefix: role for role, prefix in ID_PREFIX.items()}
# Only wolves know these, so a card for another role may not lean on them.
WOLF_ONLY = ("partner", "wolf chat", "fellow wolf", "teammate", "your wolves")
# A card is advice for a role, not for a seat: it may not name the players of any one game.
PLAYER_NAME = re.compile(r"\b(" + "|".join(DEFAULT_NAMES) + r")\b")
COACH_FOLDER = "coach"  # inside the cards folder: cards the coach wrote


class Card(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    version: int
    role: Role
    source: str
    summary: str
    instructions: str
    expected_moves: tuple[str, ...]

    @property
    def ref(self) -> str:
        """What a game log stores for a seat: the id and the version that was played."""
        return f"{self.id}@{self.version}"

    @property
    def prompt_text(self) -> str:
        return " ".join(self.instructions.split())


def check_card(card: Card) -> list[str]:
    """Everything wrong with a card, in plain words. An empty list means the card is fine."""
    problems = []
    words = len(card.instructions.split())
    if words > MAX_WORDS:
        problems.append(f"instructions are {words} words; the limit is {MAX_WORDS}")
    if not card.instructions.strip():
        problems.append("instructions are empty")
    if not card.summary.strip():
        problems.append("summary is empty")
    if not card.source.strip():
        problems.append("source is empty (credit where the idea came from)")
    if not card.id.startswith(ID_PREFIX[card.role] + "."):
        problems.append(f"id must start with '{ID_PREFIX[card.role]}.' for a {card.role.value}")
    if not card.expected_moves:
        problems.append("expected_moves is empty")
    unknown = [m for m in card.expected_moves if m not in MOVE_NAMES]
    if unknown:
        problems.append(f"unknown moves {unknown}; the moves are: {', '.join(MOVE_NAMES)}")
    named = sorted(set(PLAYER_NAME.findall(f"{card.summary} {card.instructions}")))
    if named:
        problems.append(f"the card names a player ({', '.join(named)}); say the role or the act")
    if card.role is not Role.WEREWOLF:
        text = f"{card.summary} {card.instructions}".lower()
        leaked = [w for w in WOLF_ONLY if re.search(rf"\b{re.escape(w)}", text)]
        if leaked:
            problems.append(f"a {card.role.value} card mentions wolf-only knowledge: {leaked}")
    return problems


def read_card(path: Path) -> Card:
    try:
        return Card.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"{path.name}: cannot read this card: {exc}") from exc


def load_all(directory: Path = CARDS_DIR) -> dict[str, Card]:
    """Every card in the folder, by id. Raises ValueError naming the file for the first bad one."""
    cards: dict[str, Card] = {}
    for path in sorted(directory.glob("*.yaml")):
        card = read_card(path)
        if card.id in cards:
            raise ValueError(f"{path.name}: the id '{card.id}' is used by another card too")
        problems = check_card(card)
        if problems:
            raise ValueError(f"{path.name}: " + "; ".join(problems))
        cards[card.id] = card
    return cards


def load_everywhere(directory: Path = CARDS_DIR) -> dict[str, Card]:
    """The starter cards plus the ones the coach wrote (in the coach folder), by id."""
    cards = load_all(directory)
    coach = directory / COACH_FOLDER
    if coach.is_dir():
        for card_id, card in load_all(coach).items():
            if card_id in cards:
                raise ValueError(f"the id '{card_id}' is used by another card too (coach folder)")
            cards[card_id] = card
    return cards


def write_card(card: Card, directory: Path = CARDS_DIR) -> Path:
    """Save a coach card as `<directory>/coach/<id>.yaml`. A card that fails the checks is
    refused before anything is written, and a card is never overwritten."""
    problems = check_card(card)
    if problems:
        raise ValueError(f"{card.id}: " + "; ".join(problems))
    path = directory / COACH_FOLDER / f"{card.id}.yaml"
    if path.exists():
        raise ValueError(f"{path.name} already exists; a card is never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = card.model_dump(mode="json")
    data["expected_moves"] = list(card.expected_moves)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), "utf-8")
    return path


def load_card(ref: str, directory: Path = CARDS_DIR) -> Card:
    """A card by id, or by 'id@version' as a game log stores it. Coach cards count too."""
    card_id = ref.split("@")[0]
    cards = load_everywhere(directory)
    if card_id not in cards:
        have = ", ".join(sorted(cards)) or "none"
        raise ValueError(f"no card '{card_id}'; the cards are: {have}")
    return cards[card_id]


def assign_cards(
    seat_roles: Mapping[str, Role],
    by_role: Mapping[Role, str],
    by_seat: Mapping[str, str],
    directory: Path = CARDS_DIR,
) -> dict[str, str]:
    """Which card each seat plays, as 'id@version'. A seat setting beats a role setting.
    Raises ValueError for an unknown card, an unknown seat, or a card for the wrong role."""
    wanted = {seat: by_role[role] for seat, role in seat_roles.items() if role in by_role}
    for seat, card_id in by_seat.items():
        if seat not in seat_roles:
            raise ValueError(f"no seat named '{seat}'")
        wanted[seat] = card_id
    chosen = {}
    for seat, card_id in wanted.items():
        card = load_card(card_id, directory)
        if card.role is not seat_roles[seat]:
            raise ValueError(
                f"{card.id} is a {card.role.value} card but {seat} is the {seat_roles[seat].value}"
            )
        chosen[seat] = card.ref
    return chosen
