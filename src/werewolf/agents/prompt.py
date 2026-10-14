"""Turn what one player may know into chat messages for a model.

Layout, built for prompt caching: a system message that never changes during a game (rules, who
you are, your strategy card), then a user message with what has happened, the player's private
memory, and the task. The log is append-only text, so each prompt begins with the previous one.
"""

import json
from collections.abc import Mapping, Sequence

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
)

DEFAULT_CARD = "Play to win for your team. Think about who is telling the truth and who is lying."


# One valid answer for each kind of question, with <name> standing in for a player. Mechanical
# only: they show the shape, never a strategy. A test checks each one against the answer models.
def _example(**fields: object) -> str:
    return json.dumps(fields, separators=(",", ":"))


EXAMPLES = {
    "wolf_chat": _example(
        text="Let us take <name> tonight; they argue too well.", note="<name> may be the Seer."
    ),
    "night_target": _example(target="<name>", note="Most dangerous player left."),
    "bid": _example(
        bid=1,
        message="<name>, why did you vote with the majority both days?",
        intent="ask",
        target="<name>",
        note="<name> follows the crowd.",
        beliefs=[
            {"player": "<name>", "suspicion": 0.6, "reason": "follows the crowd"},
            {"player": "<name>", "suspicion": 0.2, "reason": "open and consistent"},
        ],
    ),
    "vote": _example(
        target="<name>",
        reason="Dodged my question and changed votes.",
        note="Likely a wolf.",
        beliefs=[{"player": "<name>", "suspicion": 0.7, "reason": "dodged my question"}],
    ),
    "memory": _example(
        summary="Round 1: <name> was killed. <name> accused <name>, who denied it. "
        "Votes split, nobody removed. I trust <name>; <name> worries me."
    ),
}

QUIET_BID_EXAMPLE = _example(
    bid=0,
    message="",
    intent="none",
    target="",
    note="Nothing to add yet.",
    beliefs=[{"player": "<name>", "suspicion": 0.3, "reason": "no strong sign yet"}],
)

LEGEND = (
    'READING THE LOG: "X says (2 tokens): ..." means X won the turn by bidding 2 tokens; '
    '"X says: ..." is a message at no cost; "X replies (free): ..." is a free reply to an '
    'accusation; "Listening: A, B" means those players bid 0 on that turn; "Vote: A voted for B '
    '(reason: ...)" is a vote cast; "Morning: ..." says who died in the night; lines marked '
    "[Private] or [Wolf chat] are seen only by you (or by the two werewolves)."
)

ROLE_TEXT = {
    Role.WEREWOLF: "You are on the wolf team. Each night you and your partner choose one player "
    "to kill. You win if the wolves equal or outnumber everyone else.",
    Role.SEER: "You are on the village team. Each night you can check one player and learn their "
    "true role. You win when both werewolves are gone.",
    Role.DOCTOR: "You are on the village team. Each night you can protect one player (yourself "
    "included); a protected player cannot be killed that night. You win when both werewolves "
    "are gone.",
    Role.VILLAGER: "You are on the village team. You have no night power: use the discussion and "
    "your vote. You win when both werewolves are gone.",
}


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """A rough count: characters divided by 4."""
    return sum(len(m["content"]) for m in messages) // 4


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _speaking_rules(view: PlayerView) -> str:
    r = view.rules
    turns = f"Discussion has up to {r.speaking_turns} speaking turns each day."
    if r.speaking_mode == "floor_tokens":
        tokens = _plural(r.tokens_per_day, "floor token")
        return (
            f"{turns} Every living player starts the day with {tokens}. On each turn everyone "
            f"secretly bids 0 to {r.tokens_per_day} tokens and writes the message they would say. "
            "The highest bid speaks and pays what it bid; ties go to whoever has spoken least "
            "today, then to chance. A bid of 0 means you stay quiet and listen. Tokens you do not "
            "spend are lost at nightfall. If a message accuses someone by name (intent accuse "
            "with a target), that player gets one free reply next, once per day; free replies "
            "cost nothing. The day ends early if everyone listens."
        )
    if r.speaking_mode == "free_bid":
        return (
            f"{turns} On each turn everyone secretly bids 0 to 4 and writes the message they "
            "would say. The highest bid speaks, and bids cost nothing; ties go to whoever has "
            "spoken least today, then to chance. A bid of 0 means you stay quiet and listen. "
            "The day ends early if everyone listens."
        )
    return (
        f"{turns} Living players speak one at a time in seat order. When it is your turn you "
        "write a message, or leave it empty to stay silent."
    )


def _system(view: PlayerView, card: str) -> str:
    r = view.rules
    partner = f" Your partner is {view.partner}, the other Werewolf." if view.partner else ""
    return "\n".join(
        [
            f"You are {view.name}, a player in a game of Werewolf with 8 players: "
            f"{', '.join(view.seats)}.",
            "",
            "ROLES: 2 Werewolves, 1 Seer, 1 Doctor, 4 Villagers. The werewolves know each other "
            "and choose one player to kill each night. The Seer learns one player's true role "
            "each night. The Doctor protects one player each night. Villagers have no night power.",
            "The village wins when both werewolves are gone. The wolves win when they equal or "
            f"outnumber everyone else. If nobody has won after {r.max_rounds} rounds, the village "
            "wins.",
            "",
            "EACH ROUND: 1. Night: the wolves pick a victim, the Seer checks someone, the Doctor "
            "protects someone. 2. Morning: it is announced who died; roles of the dead stay "
            "hidden. 3. Day: players talk. 4. Vote: every living player votes to remove one player "
            "and gives a reason; the most votes is removed, and a tie removes nobody.",
            _speaking_rules(view),
            "",
            f"YOU: you are {view.name}, the {view.role.value}. {ROLE_TEXT[view.role]}{partner}",
            f"Strategy: {card or DEFAULT_CARD}",
            "",
            "HOW TO ANSWER: reply with only the JSON asked for. Messages are posted for everyone "
            f"to read, at most {r.max_message_chars} characters. Notes and belief reasons are "
            "private: nobody else will ever see them. You may lie or claim any role; that is part "
            "of the game.",
            "",
            LEGEND,
            "",
            "ANSWER EXAMPLES (use real player names in place of <name>; yours will differ):",
            f"- Night message from one werewolf to the other: {EXAMPLES['wolf_chat']}",
            f"- Choosing a night target (an empty string means none): {EXAMPLES['night_target']}",
            f"- Your turn to bid or speak: {EXAMPLES['bid']}",
            f"- Staying quiet this turn (bid 0, empty message): {QUIET_BID_EXAMPLE}",
            f"- Voting (an empty string means abstain): {EXAMPLES['vote']}",
            f"- End-of-round summary: {EXAMPLES['memory']}",
            "",
            "RULE REMINDERS: never bid more than the limit named in the question. A bid above 0 "
            "needs a message; with a bid of 0 leave the message empty. You can only target or "
            "vote for players who are alive, never for yourself. Give a belief for every other "
            "living player: a suspicion from 0 (trust) to 1 (sure they are a wolf) and a reason "
            f"of at most {REASON_MAX} characters. Keep notes to {NOTE_MAX} characters. Use only "
            "what the log shows: do not invent events, earlier days, or things people did not "
            "say. At the start of day 1 nobody has spoken yet. Write like a person at the "
            "table: short, direct sentences, no speeches.",
        ]
    )


def _events(view: PlayerView, from_round: int) -> str:
    lines: list[str] = []
    quiet: list[str] = []
    last_round = 0

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
            if event.reply:
                lines.append(f"{event.speaker} replies (free): {event.text}")
            elif event.paid:
                paid = _plural(event.paid, "token")
                lines.append(f"{event.speaker} says ({paid}): {event.text}")
            else:
                lines.append(f"{event.speaker} says: {event.text}")
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
    return "\n".join(lines) if lines else "Nothing yet."


def _memory(
    view: PlayerView, beliefs: Mapping[str, Belief], summary: str, notes: Sequence[str]
) -> str:
    parts = []
    if summary:
        parts.append(f"Summary of earlier rounds: {summary}")
    known = [n for n in view.seats if n in beliefs and n != view.name]
    if known:
        parts.append("Your suspicions (0 = trust, 1 = sure they are a wolf):")
        parts += [f"- {n}: {beliefs[n].suspicion:g} ({beliefs[n].reason})" for n in known]
    if notes:
        parts.append("Your recent private notes (oldest first):")
        parts += [f"- {note}" for note in notes]
    return "\n".join(parts) if parts else "Nothing yet."


def _beliefs_ask() -> str:
    return (
        f"Write a private note (at most {NOTE_MAX} characters) and a belief about each other "
        f"living player: a suspicion from 0 to 1 and a reason of at most {REASON_MAX} characters."
    )


def _bid_ask(view: PlayerView, task: BidTask) -> str:
    intents = (
        "Choose an intent (private): accuse, defend, share_info, ask, or none, and a target "
        "name or an empty string."
    )
    fields = "JSON fields: bid, message, intent, target, note, beliefs."
    if task.reply_to:
        head = (
            f"{task.reply_to} accused you (their message is in the log above). This free reply is "
            f"your chance to answer the accusation: write your message (at most {task.max_chars} "
            "characters). Leaving it empty means you give no answer. It is a free turn, so use "
            "bid 0."
        )
    elif task.free:
        head = (
            "It is your turn to speak (a free turn, so use bid 0). Write your message (at most "
            f"{task.max_chars} characters), or leave it empty to stay silent."
        )
    elif view.rules.speaking_mode == "floor_tokens" and task.max_bid == 0:
        head = (
            "You have no floor tokens left today, so you cannot speak this turn: bid 0 and leave "
            "the message empty."
        )
    elif view.rules.speaking_mode == "floor_tokens":
        tokens = _plural(task.max_bid, "floor token")
        head = (
            f"You have {tokens} left today. Bid 0 to {task.max_bid}: 0 means you stay quiet and "
            "listen; the highest bid speaks and pays what it bid. Your message (at most "
            f"{task.max_chars} characters) is posted only if you win the turn. If you bid above 0 "
            "you must write a message; if you have nothing to say, bid 0."
        )
    else:
        head = (
            f"Bid 0 to {task.max_bid}: bids cost nothing; 0 means you stay quiet and listen; the "
            f"highest bid speaks. Your message (at most {task.max_chars} characters) is posted "
            "only if you win the turn. If you bid above 0 you must write a message; if you have "
            "nothing to say, bid 0."
        )
    return f"{head} {intents} {_beliefs_ask()} {fields}"


def _task(view: PlayerView, task: Task) -> str:
    if isinstance(task, WolfChatTask):
        return (
            f"It is night. Write one private message to your partner {view.partner} (at most "
            f"{task.max_chars} characters) about who to kill and why. Only the two of you can "
            f"read it. Also write a private note (at most {NOTE_MAX} characters). "
            "JSON fields: text, note."
        )
    if isinstance(task, NightTargetTask):
        what = {
            "kill": "Choose which player the wolves kill tonight.",
            "check": "Choose one player to check tonight; you will learn their true role.",
            "protect": "Choose one player to protect tonight (you may protect yourself).",
        }[task.purpose]
        return (
            f"{what} Options: {', '.join(task.options)}. Use an empty string for no target. "
            f"Add a private note (at most {NOTE_MAX} characters). JSON fields: target, note."
        )
    if isinstance(task, BidTask):
        return _bid_ask(view, task)
    if isinstance(task, MemoryTask):
        return (
            f"The round is over. Write a short summary (at most {task.max_chars} characters) of "
            "everything that matters for winning: who died, who accused or defended whom, claims "
            "about roles, how people voted, and your suspicions. It replaces your earlier summary, "
            "so keep what is still important. JSON fields: summary."
        )
    assert isinstance(task, VoteTask)
    return (
        f"Vote to remove one player. Options: {', '.join(task.options)}. You cannot vote for "
        "yourself or for a dead player. Use an empty string to abstain. Give a reason of at most "
        f"100 characters. {_beliefs_ask()} "
        "JSON fields: target, reason, note, beliefs."
    )


def build_messages(
    view: PlayerView,
    task: Task,
    *,
    card: str = "",
    beliefs: Mapping[str, Belief] | None = None,
    summary: str = "",
    notes: Sequence[str] = (),
    from_round: int = 1,
) -> list[dict[str, str]]:
    dead = ", ".join(view.dead) or "nobody"
    now = f"Round {view.round}. Alive: {', '.join(view.alive)}. Dead: {dead}.\n{_task(view, task)}"
    if task.error:
        now += f"\n\nYour last answer was rejected: {task.error}. Answer again and fix that."
    user = "\n\n".join(
        [
            f"## What has happened\n{_events(view, from_round)}",
            f"## Your private memory\n{_memory(view, beliefs or {}, summary, notes)}",
            f"## Now\n{now}",
        ]
    )
    return [
        {"role": "system", "content": _system(view, card)},
        {"role": "user", "content": user},
    ]
