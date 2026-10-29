"""The tables. Logs and tag files are kept as the exact text of their JSON, so a game read back
is byte for byte the game that was written (a JSON column may reorder keys)."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

games = Table(
    "games",
    metadata,
    Column("id", String(32), primary_key=True),  # "<seed>-<8 hex of the log's hash>"
    Column("seed", Integer, nullable=False, index=True),
    Column("winner", String(16), nullable=False),
    Column("rounds", Integer, nullable=False),
    Column("model", String(64), nullable=False, default=""),
    Column("cards", JSON, nullable=False),  # seat -> "id@version"
    Column(
        "card_ids", Text, nullable=False, default=""
    ),  # "|wolf.a|villager.b|": to filter by card
    Column("cost", Float, nullable=False, default=0.0),
    Column("clean", Boolean, nullable=False),
    Column("rule_version", String(8), nullable=False),
    Column("source", String(128), nullable=False, default=""),  # the folder it came from
    Column("status", String(16), nullable=False, default="finished"),
    Column("human_seat", String(32), nullable=True),
    Column("log", Text, nullable=False),
)

tags = Table(
    "tags",
    metadata,
    Column("game_id", String(32), ForeignKey("games.id"), primary_key=True),
    Column("tagfile", Text, nullable=False),
)

coach_generations = Table(
    "coach_generations",
    metadata,
    Column("side", String(16), primary_key=True),
    Column("number", Integer, primary_key=True),
    Column("record", Text, nullable=False),
)

# A game is real only when it finished: stopped games stay in `games` but out of every list.
finished = games.c.status == "finished"

play_sessions = Table(
    "play_sessions",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("status", String(16), nullable=False),  # running, finished or stopped
    Column("game_id", String(32), nullable=True),  # the stored game, once it finished
    Column("reason", Text, nullable=False, default=""),  # why it stopped
    Column("cards", JSON, nullable=False),  # what the visitor picked
    Column("cost", Float, nullable=False, default=0.0),
    Column("created_at", Float, nullable=False),
)
