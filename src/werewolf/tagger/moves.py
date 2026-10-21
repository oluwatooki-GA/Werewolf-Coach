"""The persuasion moves (DESIGN 3.5): the one list that cards, the tagger and the reports share.

The names, meanings and examples are in prompts/moves.yaml.
"""

from werewolf.prompts import load

# (name, family, what it is, an example line)
MOVES: tuple[tuple[str, str, str, str], ...] = tuple(
    (m["name"], m["family"], m["what"], m["example"]) for m in load("moves")["moves"]
)

MOVE_NAMES: tuple[str, ...] = tuple(m[0] for m in MOVES)
CLAIM_MOVES = ("role_claim", "result_claim")
ACCUSE_MOVES = ("accuse_reasoned", "accuse_bare")
