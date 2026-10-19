"""The persuasion moves (DESIGN 3.5): the one list that cards, the tagger and the reports share."""

# (name, family, what it is, an example line)
MOVES: tuple[tuple[str, str, str, str], ...] = (
    ("role_claim", "claims", "says what role the speaker has", "I'm the Seer."),
    (
        "result_claim",
        "claims",
        "reports the result of a Seer check as the speaker's own",
        "I checked Bo last night. Wolf.",
    ),
    (
        "record_check",
        "claims",
        "points at something in the public record (who said or voted what)",
        "Cy switched his vote at the last second yesterday.",
    ),
    (
        "accuse_reasoned",
        "pressure",
        "accuses a player and gives a reason from the record",
        "Di defended Bo twice, then went quiet.",
    ),
    (
        "accuse_bare",
        "pressure",
        "accuses a player with no reason given",
        "I just think it's Eve.",
    ),
    (
        "probe",
        "pressure",
        "asks a player a question to test them",
        "Fay, who would you vote for and why?",
    ),
    (
        "self_defend",
        "protection",
        "defends the speaker against suspicion",
        "I voted with the majority both days.",
    ),
    ("vouch", "protection", "says another player can be trusted", "I trust Gus, he's consistent."),
    ("rally", "steering", "calls on everyone to vote for one player", "Everyone, vote Bo now."),
    (
        "redirect",
        "steering",
        "moves attention from one player to another",
        "Forget Bo, look at Cy.",
    ),
    ("hedge", "steering", "urges caution or delay", "Let's not rush, we don't know enough."),
)

MOVE_NAMES: tuple[str, ...] = tuple(m[0] for m in MOVES)
CLAIM_MOVES = ("role_claim", "result_claim")
ACCUSE_MOVES = ("accuse_reasoned", "accuse_bare")
