"""Turn what one player may know into chat messages for a model.

Layout, built for prompt caching: a system message that never changes during a game (rules, who
you are, your strategy card), then a user message with what has happened, the player's private
memory, and the task. The log is append-only text, so each prompt begins with the previous one.

The wording is in src/werewolf/prompts/player.yaml. This file decides which pieces to use, fills
in their placeholders, and formats the events of the game.
"""

import json
from collections.abc import Mapping, Sequence

from werewolf.agents.persona import describe
from werewolf.agents.wire import NOTE_MAX, REASON_MAX
from werewolf.engine.actions import (
    Belief,
    BidTask,
    MemoryTask,
    NightTargetTask,
    Task,
    VoteTask,
    WolfChatTask,
)
from werewolf.engine.views import (
    Death,
    GameOver,
    Listening,
    NoDeath,
    NoRemoval,
    PlayerView,
    Removal,
    Role,
    SeerResult,
    Speech,
    VoteCast,
    WolfChat,
    numbered_speeches,
    round_record,
)
from werewolf.prompts import load, text

PLAYER = "player"  # the YAML file the wording lives in
DEFAULT_CARD = text(PLAYER, "default_card")


def _t(key: str, **values: object) -> str:
    return text(PLAYER, key, **values)


def _example(fields: object) -> str:
    return json.dumps(fields, separators=(",", ":"))


# One valid answer for each kind of question, with <name> standing in for a player. Mechanical
# only: they show the shape, never a strategy. A test checks each one against the answer models.
_EXAMPLES = load(PLAYER)["examples"]
EXAMPLES = {
    kind: _example(_EXAMPLES[kind]["fields"])
    for kind in ("wolf_chat", "night_target", "bid", "vote", "memory")
}
QUIET_BID_EXAMPLE = _example(_EXAMPLES["quiet_bid"]["fields"])

LEGEND = _t("legend_reading") + "\n\n" + _t("legend_citing")

ROLE_TEXT = {role: load(PLAYER)["role_text"][role.value] for role in Role}


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """A rough count: characters divided by 4."""
    return sum(len(m["content"]) for m in messages) // 4


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _speaking_rules(view: PlayerView) -> str:
    r = view.rules
    if r.speaking_mode == "floor_tokens":
        tokens = _plural(r.tokens_per_day, "floor token")
        return _t(
            "speaking_floor_tokens",
            turns=r.speaking_turns,
            tokens=tokens,
            max_bid=r.tokens_per_day,
        )
    if r.speaking_mode == "free_bid":
        return _t("speaking_free_bid", turns=r.speaking_turns)
    return _t("speaking_fixed_order", turns=r.speaking_turns)


def _system(view: PlayerView, card: str, persona: str = "") -> str:
    r = view.rules
    partner = _t("partner", partner=view.partner) if view.partner else ""
    return "\n".join(
        [
            _t("intro", name=view.name, seats=", ".join(view.seats)),
            "",
            _t("roles"),
            _t("win", max_rounds=r.max_rounds),
            "",
            _t("each_round"),
            _speaking_rules(view),
            "",
            _t(
                "you",
                name=view.name,
                role=view.role.value,
                role_text=ROLE_TEXT[view.role],
                partner=partner,
            ),
            _t("strategy", card=card or DEFAULT_CARD),
            *([_t("manner", manner=describe(persona)), _t("manner_note")] if persona else []),
            "",
            _t("how_to_answer", max_chars=r.max_message_chars),
            "",
            LEGEND,
            "",
            _t("examples_header"),
            *(
                f"- {_EXAMPLES[kind]['label']}: {example}"
                for kind, example in (
                    ("wolf_chat", EXAMPLES["wolf_chat"]),
                    ("night_target", EXAMPLES["night_target"]),
                    ("bid", EXAMPLES["bid"]),
                    ("quiet_bid", QUIET_BID_EXAMPLE),
                    ("vote", EXAMPLES["vote"]),
                    ("memory", EXAMPLES["memory"]),
                )
            ),
            "",
            _t(
                "reminders",
                reason_max=REASON_MAX,
                note_max=NOTE_MAX,
                belief_rule=_t(
                    "belief_rule_wolf" if view.partner else "belief_rule", reason_max=REASON_MAX
                ),
            ),
        ]
    )


def _events(view: PlayerView, from_round: int) -> str:
    lines: list[str] = []
    quiet: list[str] = []
    last_round = 0
    numbers = {id(speech): line for line, speech in numbered_speeches(view.events)}

    def flush() -> None:
        if quiet:
            lines.append(f"Listening: {', '.join(quiet)}")
            quiet.clear()

    for event in view.events:
        if event.round < from_round:
            continue
        if isinstance(event, Listening):
            quiet.append(event.player)
            continue
        flush()
        if event.round != last_round:
            last_round = event.round
            lines.append(f"--- Round {event.round} ---")
        if isinstance(event, WolfChat):
            lines.append(
                f"[Wolf chat, private to you and your partner] {event.speaker}: {event.text}"
            )
        elif isinstance(event, SeerResult):
            lines.append(f"[Private] You checked {event.target}: they are a {event.role.value}.")
        elif isinstance(event, Death):
            lines.append(f"Morning: {event.player} was killed in the night.")
        elif isinstance(event, NoDeath):
            lines.append("Morning: nobody died in the night.")
        elif isinstance(event, Speech):
            number = f"[{numbers[id(event)]}] " if id(event) in numbers else ""
            if event.reply:
                lines.append(f"{number}{event.speaker} replies (free): {event.text}")
            elif event.paid:
                paid = _plural(event.paid, "token")
                lines.append(f"{number}{event.speaker} says ({paid}): {event.text}")
            else:
                lines.append(f"{number}{event.speaker} says: {event.text}")
        elif isinstance(event, VoteCast):
            if event.target is None:
                lines.append(f"Vote: {event.voter} abstained.")
            else:
                why = f" (reason: {event.reason})" if event.reason else ""
                lines.append(f"Vote: {event.voter} voted for {event.target}{why}.")
        elif isinstance(event, Removal):
            lines.append(f"{event.player} was removed by the vote.")
        elif isinstance(event, NoRemoval):
            lines.append("Nobody was removed by the vote.")
        elif isinstance(event, GameOver):
            lines.append(f"The game is over: {event.winner.value} wins.")
    flush()
    return "\n".join(lines) if lines else _t("nothing_yet")


def _record(view: PlayerView, from_round: int) -> str:
    """What the game wrote down about the rounds whose log is no longer shown."""
    rounds = range(1, min(from_round, view.round))
    if not rounds:
        return ""
    lines = [round_record(view.events, r) for r in rounds]
    return _t("record_header") + "\n" + "\n".join(lines)


def _memory(
    view: PlayerView, beliefs: Mapping[str, Belief], summary: str, notes: Sequence[str]
) -> str:
    parts = []
    if summary:
        parts.append(_t("memory_summary", summary=summary))
    known = [n for n in view.seats if n in beliefs and n != view.name and n in view.alive]
    if known:
        parts.append(_t("memory_beliefs_wolf" if view.partner else "memory_beliefs"))
        parts += [f"- {n}: {beliefs[n].suspicion:g} ({beliefs[n].reason})" for n in known]
    if notes:
        parts.append(_t("memory_notes"))
        parts += [f"- {note}" for note in notes]
    return "\n".join(parts) if parts else _t("nothing_yet")


def _beliefs_ask(view: PlayerView) -> str:
    key = "beliefs_ask_wolf" if view.partner else "beliefs_ask"
    return _t(key, note_max=NOTE_MAX, reason_max=REASON_MAX)


def _day_status(view: PlayerView) -> str:
    """A plain statement, written by the game, of what has been said today. Without it a model
    that finds nothing under "What has happened" tends to invent earlier talk."""
    today = [line for line, speech in numbered_speeches(view.events) if speech.round == view.round]
    if not today:
        if numbered_speeches(view.events):
            return _t("day_nobody")
        died = _t("day_died", dead=", ".join(view.dead)) if view.dead else ""
        return _t("day_first", died=died)
    span = today[0] if len(today) == 1 else f"{today[0]} to {today[-1]}"
    return _t("day_some", messages=_plural(len(today), "message"), span=span)


def _bid_ask(view: PlayerView, task: BidTask) -> str:
    others = ", ".join(n for n in view.alive if n != view.name)
    intents = _t("bid_intents", others=others)
    latest = [f"{line} ({s.speaker})" for line, s in numbered_speeches(view.events)[-4:]]
    fields = _t("bid_fields") + (
        _t("bid_fields_latest", latest=", ".join(latest)) if latest else ""
    )
    if task.reply_to:
        head = _t("bid_reply", accuser=task.reply_to, max_chars=task.max_chars)
    elif task.free:
        head = _t("bid_free", max_chars=task.max_chars)
    elif view.rules.speaking_mode == "floor_tokens" and task.max_bid == 0:
        head = _t("bid_no_tokens")
    elif view.rules.speaking_mode == "floor_tokens":
        head = _t(
            "bid_tokens",
            tokens=_plural(task.max_bid, "floor token"),
            max_bid=task.max_bid,
            max_chars=task.max_chars,
        )
    else:
        head = _t("bid_free_bid", max_bid=task.max_bid, max_chars=task.max_chars)
    return f"{_day_status(view)} {head} {intents} {_beliefs_ask(view)} {fields}"


def _task(view: PlayerView, task: Task) -> str:
    if isinstance(task, WolfChatTask):
        why = _t("wolf_chat_no_read") if view.round == 1 else _t("wolf_chat_why")
        return _t(
            "wolf_chat",
            partner=view.partner,
            max_chars=task.max_chars,
            why=why,
            note_max=NOTE_MAX,
        )
    if isinstance(task, NightTargetTask):
        what = _t(
            {"kill": "night_kill", "check": "night_check", "protect": "night_protect"}[task.purpose]
        )
        if view.round == 1:
            what += f" {_t('night_no_read')}"
        return _t("night_target", what=what, options=", ".join(task.options), note_max=NOTE_MAX)
    if isinstance(task, BidTask):
        return _bid_ask(view, task)
    if isinstance(task, MemoryTask):
        return _t("memory_task", max_chars=task.max_chars)
    assert isinstance(task, VoteTask)
    return _t("vote_task", options=", ".join(task.options), beliefs=_beliefs_ask(view))


def build_messages(
    view: PlayerView,
    task: Task,
    *,
    card: str = "",
    persona: str = "",
    beliefs: Mapping[str, Belief] | None = None,
    summary: str = "",
    notes: Sequence[str] = (),
    from_round: int = 1,
) -> list[dict[str, str]]:
    dead = ", ".join(view.dead) or "nobody"
    now = (
        _t("now", round=view.round, alive=", ".join(view.alive), dead=dead)
        + "\n"
        + _task(view, task)
    )
    if card and not isinstance(task, MemoryTask):  # said again at the moment of choosing
        now += "\n" + _t("strategy_again", card=card)
    if view.partner and isinstance(task, BidTask):
        now += "\n" + _t("wolf_reminder")
    if task.error:
        now += "\n\n" + _t("rejected", error=task.error)
    record = _record(view, from_round)
    user = "\n\n".join(
        ([record] if record else [])
        + [
            f"## What has happened\n{_events(view, from_round)}",
            f"## Your private memory\n{_memory(view, beliefs or {}, summary, notes)}",
            f"## Now\n{now}",
        ]
    )
    return [
        {"role": "system", "content": _system(view, card, persona)},
        {"role": "user", "content": user},
    ]
