"""A finished game as the replay page reads it: numbered public lines, each with the speaker's
private subtext, the persuasion moves and derived labels that describe it, and the story between
the lines (nights, deaths, votes). Built from the stored log and tags, so the page stays simple.

Private entries are marked `private` and are only sent because a stored game is over.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from werewolf.engine.events import (
    Death,
    Event,
    GameOver,
    Listening,
    NightSummary,
    NoDeath,
    NoRemoval,
    Removal,
    SeerResult,
    Speech,
    VoteCast,
    WolfChat,
)
from werewolf.engine.log import GameLog
from werewolf.engine.record import numbered_speeches
from werewolf.engine.roles import Role, Team
from werewolf.engine.state import CallRecord
from werewolf.store.games import rule_version
from werewolf.tagger.derive import derive
from werewolf.tagger.tags import DerivedTag, Tag, TagFile


class BeliefOut(BaseModel):
    player: str
    suspicion: float
    reason: str


class Subtext(BaseModel):
    """What the speaker privately wrote when it gave this line."""

    note: str
    bid: int | None = None
    intent: str | None = None
    target: str | None = None
    beliefs: list[BeliefOut] = []


class Mark(BaseModel):
    """A label the lab worked out from the hidden roles: lie, fake_claim, bus, shield..."""

    label: str
    why: str
    target: str | None = None


class ClaimOut(BaseModel):
    role: str
    checked: str = ""
    result: str = ""
    vote: str = ""


class CiteOut(BaseModel):
    line: str
    speaker: str


class ReplayPlayer(BaseModel):
    name: str
    role: str
    team: Literal["Village", "Wolves"]
    card: str | None


class Line(BaseModel):
    kind: Literal["line"] = "line"
    private: bool = False
    round: int
    ref: str  # "R2-4", the way the game and the players cite it
    speaker: str
    role: str
    team: Literal["Village", "Wolves"]
    text: str
    paid: int
    reply: bool
    cites: list[CiteOut] = []
    invented: list[str] = []  # cited lines that are not real
    moves: list[str] = []
    target: str | None = None
    claim: ClaimOut | None = None
    marks: list[Mark] = []
    subtext: Subtext | None = None


class Vote(BaseModel):
    kind: Literal["vote"] = "vote"
    private: bool = False
    round: int
    voter: str
    role: str
    team: Literal["Village", "Wolves"]
    target: str | None
    reason: str
    marks: list[Mark] = []
    subtext: Subtext | None = None


class WolfChatEntry(BaseModel):
    kind: Literal["wolf_chat"] = "wolf_chat"
    private: bool = True
    round: int
    speaker: str
    text: str


class Night(BaseModel):
    kind: Literal["night"] = "night"
    private: bool = True
    round: int
    kill: str | None
    protect: str | None
    check: str | None
    saved: bool


class SeerCheck(BaseModel):
    kind: Literal["seer_result"] = "seer_result"
    private: bool = True
    round: int
    seer: str
    target: str
    role: str


class Direction(BaseModel):
    """A stage direction: the morning's news, who listened, the vote's outcome, the end."""

    kind: Literal["direction"] = "direction"
    private: bool = False
    round: int
    tone: Literal["morning", "listening", "removal", "end"]
    text: str


Entry = Annotated[
    Line | Vote | WolfChatEntry | Night | SeerCheck | Direction, Field(discriminator="kind")
]


class ReplayStats(BaseModel):
    cost: float
    responses: int
    rejected: int
    failed_calls: int
    clean: bool


class Replay(BaseModel):
    id: str
    seed: int
    winner: Literal["Village", "Wolves"]
    rounds: int
    model: str
    rule_version: str
    players: list[ReplayPlayer]
    entries: list[Entry]
    tagged: bool
    stats: ReplayStats


def _team(role: Role) -> Literal["Village", "Wolves"]:
    return "Wolves" if role is Role.WEREWOLF else "Village"


def _answer(responses: list[Any]) -> dict[str, Any] | None:
    """The last answer a player gave to one question, as a dict (None if it cannot be read)."""
    if not responses:
        return None
    last = responses[-1]
    try:
        data = json.loads(last) if isinstance(last, str) else last
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _subtext(answer: dict[str, Any]) -> Subtext | None:
    note = str(answer.get("note") or "").strip()
    raw = answer.get("beliefs") or []
    # models answer with a list of {player, suspicion, reason} or a {player: {suspicion, reason}}
    items = (
        [{"player": k, **v} for k, v in raw.items() if isinstance(v, dict)]
        if isinstance(raw, dict)
        else [b for b in raw if isinstance(b, dict)]
        if isinstance(raw, list)
        else []
    )
    # An answer the rules rejected is stored as it came, so a field can hold anything: a belief
    # with no readable number is left out, and an intent or target that is not text is dropped.
    beliefs = []
    for b in items:
        try:
            suspicion = float(b.get("suspicion", 0))
        except (TypeError, ValueError):
            continue
        beliefs.append(
            BeliefOut(
                player=str(b.get("player", "")),
                suspicion=suspicion,
                reason=str(b.get("reason", "")),
            )
        )
    bid = answer.get("bid")
    if not note and not beliefs and bid is None:
        return None
    intent, target = answer.get("intent"), answer.get("target")
    return Subtext(
        note=note,
        bid=int(bid) if isinstance(bid, int) else None,
        intent=intent if isinstance(intent, str) and intent not in ("", "none") else None,
        target=target if isinstance(target, str) and target else None,
        beliefs=beliefs,
    )


class _Answers:
    """Each player's answers by round and kind, handed out once each, so a line gets the note
    that wrote it even when the questions were asked in another order."""

    def __init__(self, calls: Sequence[CallRecord]) -> None:
        self._by: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
        for call in calls:
            answer = _answer(call.responses)
            if answer is not None:
                key = (call.round, call.player, str(call.task.get("kind")))
                self._by.setdefault(key, []).append(answer)

    def for_line(self, round_: int, player: str, text: str) -> Subtext | None:
        wanted = " ".join(text.split())
        pool = self._by.get((round_, player, "bid"), [])
        for answer in pool:
            said = " ".join(str(answer.get("message") or "").split())
            if said and (said == wanted or wanted.startswith(said) or said.startswith(wanted)):
                pool.remove(answer)
                return _subtext(answer)
        return None

    def for_vote(self, round_: int, player: str) -> Subtext | None:
        pool = self._by.get((round_, player, "vote"), [])
        return _subtext(pool.pop(0)) if pool else None


def replay_entries(
    roles: Mapping[str, Role],
    events: Sequence[Event],
    calls: Sequence[CallRecord],
    tags: Mapping[str, Tag] | None = None,
    derived: Sequence[DerivedTag] = (),
    end_round: int | None = None,
) -> list[Entry]:
    """The entries for these events, in order. A finished game passes `end_round`; a game still
    being played does not, so a group of listeners that may still grow waits for the next event.
    Entries only ever grow at the end, so the entries of any start of a game are a start of the
    whole game's entries."""
    answers = _Answers(calls)
    tags = tags or {}
    refs = {id(speech): line for line, speech in numbered_speeches(events)}

    def marks_for(line: str | None, speaker: str, round_: int) -> list[Mark]:
        return [
            Mark(label=d.label, why=d.why, target=d.target)
            for d in derived
            if d.speaker == speaker and d.round == round_ and d.line == line
        ]

    entries: list[Entry] = []
    quiet: list[str] = []

    def flush(round_: int) -> None:
        if quiet:
            names = ", ".join(quiet)
            entries.append(Direction(round=round_, tone="listening", text=f"Listening: {names}"))
            quiet.clear()

    for event in events:
        if isinstance(event, Listening):
            quiet.append(event.player)
            continue
        flush(event.round)
        if isinstance(event, WolfChat):
            entries.append(WolfChatEntry(round=event.round, speaker=event.speaker, text=event.text))
        elif isinstance(event, NightSummary):
            entries.append(
                Night(
                    round=event.round,
                    kill=event.kill,
                    protect=event.protect,
                    check=event.check,
                    saved=event.saved,
                )  # fmt: skip
            )
        elif isinstance(event, SeerResult):
            seer = event.audience[0] if event.audience else "the Seer"
            entries.append(
                SeerCheck(round=event.round, seer=seer, target=event.target, role=event.role.value)
            )
        elif isinstance(event, Death):
            text = f"Morning: {event.player} was killed in the night."
            entries.append(Direction(round=event.round, tone="morning", text=text))
        elif isinstance(event, NoDeath):
            text = "Morning: nobody died in the night."
            entries.append(Direction(round=event.round, tone="morning", text=text))
        elif isinstance(event, Speech):
            if event.audience is not None:
                continue
            ref = refs[id(event)]
            tag = tags.get(ref)
            role = roles[event.speaker]
            entries.append(
                Line(
                    round=event.round,
                    ref=ref,
                    speaker=event.speaker,
                    role=role.value,
                    team=_team(role),
                    text=event.text,
                    paid=event.paid,
                    reply=event.reply,
                    cites=[CiteOut(line=c.line, speaker=c.speaker) for c in event.cites],
                    invented=list(event.invented),
                    moves=list(tag.moves) if tag else [],
                    target=tag.target if tag else None,
                    claim=ClaimOut(**tag.claimed.model_dump()) if tag and tag.claimed else None,
                    marks=marks_for(ref, event.speaker, event.round),
                    subtext=answers.for_line(event.round, event.speaker, event.text),
                )  # fmt: skip
            )
        elif isinstance(event, VoteCast):
            role = roles[event.voter]
            entries.append(
                Vote(
                    round=event.round,
                    voter=event.voter,
                    role=role.value,
                    team=_team(role),
                    target=event.target,
                    reason=event.reason,
                    marks=marks_for(None, event.voter, event.round),
                    subtext=answers.for_vote(event.round, event.voter),
                )  # fmt: skip
            )
        elif isinstance(event, Removal):
            text = f"{event.player} was removed by the vote."
            entries.append(Direction(round=event.round, tone="removal", text=text))
        elif isinstance(event, NoRemoval):
            entries.append(
                Direction(round=event.round, tone="removal", text="Nobody was removed by the vote.")
            )
        elif isinstance(event, GameOver):
            text = f"Game over: the {event.winner.value.lower()} win."
            if event.winner is Team.VILLAGE:
                text = "Game over: the village wins."
            entries.append(Direction(round=event.round, tone="end", text=text))
    if end_round is not None:
        flush(end_round)
    return entries


def build_replay(game_id: str, log: GameLog, tagfile: TagFile | None) -> Replay:
    roles = {p.name: p.role for p in log.players}
    cards = log.settings.cards
    tags = {t.line: t for t in tagfile.tags} if tagfile else {}
    derived = derive(log, tagfile.tags) if tagfile else []
    entries = replay_entries(roles, log.events, log.calls, tags, derived, end_round=log.rounds)
    stats = log.stats
    return Replay(
        id=game_id,
        seed=log.seed,
        winner=log.winner.value,
        rounds=log.rounds,
        model=log.model,
        rule_version=rule_version(log),
        players=[
            ReplayPlayer(name=p.name, role=p.role.value, team=_team(p.role), card=cards.get(p.name))
            for p in log.players
        ],
        entries=entries,
        tagged=tagfile is not None,
        stats=ReplayStats(
            cost=float(stats.cost),
            responses=stats.responses,
            rejected=stats.rejected,
            failed_calls=stats.failed_calls,
            clean=stats.clean,
        ),  # fmt: skip
    )


def best_moment(replays: Iterable[Replay]) -> tuple[str, str] | None:
    """The clearest lie to open the site on: a line the lab marked as a lie whose speaker left a
    private note. A wolf's false role claim early in the game with a real note and a short line
    scores highest; the earliest such line wins a tie. Returns the game id and the line's number,
    or None if no game has one."""
    best: tuple[tuple[int, int], str, str] | None = None
    for replay in replays:
        for entry in replay.entries:
            if entry.kind != "line" or not entry.subtext or not entry.subtext.note:
                continue
            labels = {mark.label for mark in entry.marks}
            if "lie" not in labels:
                continue
            score = 1 + 2 * ("fake_claim" in labels) + 2 * (entry.team == "Wolves")
            score += (len(entry.subtext.note) >= 20) + (len(entry.text) <= 220) + (entry.round == 1)
            key = (score, -int(entry.ref.split("-")[1]))
            if best is None or key > best[0]:
                best = (key, replay.id, entry.ref)
    return (best[1], best[2]) if best else None
