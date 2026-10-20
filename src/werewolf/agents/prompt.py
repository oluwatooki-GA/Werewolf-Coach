"""Turn what one player may know into chat messages for a model.

Layout, built for prompt caching: a system message that never changes during a game (rules, who
you are, your strategy card), then a user message with what has happened, the player's private
memory, and the task. The log is append-only text, so each prompt begins with the previous one.
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

DEFAULT_CARD = "Play to win for your team. Think about who is telling the truth and who is lying."


# One valid answer for each kind of question, with <name> standing in for a player. Mechanical
# only: they show the shape, never a strategy. A test checks each one against the answer models.
def _example(**fields: object) -> str:
    return json.dumps(fields, separators=(",", ":"))


EXAMPLES = {
    "wolf_chat": _example(
        text="Let us take <name> tonight.", note="A plain pick, no read on anyone yet."
    ),
    "night_target": _example(target="<name>", note="Pick for tonight."),
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
        cites=[{"line": "R1-2", "speaker": "<name>"}],
    ),
    "vote": _example(
        target="<name>",
        reason="Dodged my question and changed votes.",
        note="Likely a wolf.",
        beliefs=[{"player": "<name>", "suspicion": 0.7, "reason": "dodged my question"}],
    ),
    "memory": _example(
        summary="<name> answered every question and I trust them. <name> dodged twice and "
        "worries me. Next: ask <name> why they stayed quiet."
    ),
}

QUIET_BID_EXAMPLE = _example(
    bid=0,
    message="",
    intent="none",
    target="",
    note="Nothing to add yet.",
    beliefs=[{"player": "<name>", "suspicion": 0.3, "reason": "no strong sign yet"}],
    cites=[],
)

LEGEND = (
    'READING THE LOG: "X says (2 tokens): ..." means X won the turn by bidding 2 tokens; '
    '"X says: ..." is a message at no cost; "X replies (free): ..." is a free reply to an '
    'accusation; "Listening: A, B" means those players chose to stay quiet that turn; '
    '"Vote: A voted for B (reason: ...)" is a vote cast; "Morning: ..." says who died in the '
    "night; lines marked [Private] or [Wolf chat] are seen only by you (or by the two "
    "werewolves). Each message "
    "starts with its number, such as [R2-4] (round 2, message 4). The game record, when there is "
    "one, was written by the game and is always accurate; role claims in it are what players said "
    "about themselves, not proof.\n\n"
    "CITING: when your message points at something a player "
    'said, add it to "cites" as {"line": "R2-4", "speaker": "Bo"}: the number and the player '
    "who wrote that line. The game checks every cite and marks a wrong one as invented. Cite only "
    "lines you can see. Use [] when you cite nothing. An accusation (intent accuse) must cite "
    "the numbered line it rests on."
)

ROLE_TEXT = {
    Role.WEREWOLF: "You are on the wolf team. Each night you and your partner choose one player "
    "to kill. You win if the wolves equal or outnumber everyone else. Never quote or hint at "
    "your private wolf chat in public, and in public treat your partner like any other player.",
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
            "spend are lost at nightfall, so unless your strategy says otherwise, spend them: "
            "bid 1 to 3 when you have a question, a read or an answer to give. If a message "
            "accuses someone by name (intent accuse "
            "with a target), that player gets one free reply next, once per day; free replies "
            "cost nothing. The day ends early if everyone listens, and a day with no talk gives "
            "the village nothing to vote on, which only helps the wolves."
        )
    if r.speaking_mode == "free_bid":
        return (
            f"{turns} On each turn everyone secretly bids 0 to 4 and writes the message they "
            "would say. The highest bid speaks, and bids cost nothing; ties go to whoever has "
            "spoken least today, then to chance. A bid of 0 means you stay quiet and listen. "
            "The day ends early if everyone listens, and a day with no talk gives the village "
            "nothing to vote on, which only helps the wolves."
        )
    return (
        f"{turns} Living players speak one at a time in seat order. When it is your turn you "
        "write a message, or leave it empty to stay silent."
    )


def _system(view: PlayerView, card: str, persona: str = "") -> str:
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
            *(
                [
                    f"Table manner: {describe(persona)}",
                    "Your strategy decides what you try to do and how much you speak; your "
                    "manner only decides how you sound.",
                ]
                if persona
                else []
            ),
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
            "RULE REMINDERS: you can only target or vote for players who are alive, never for "
            "yourself. Give a belief for every other living player: a suspicion from 0 (trust) "
            "to 1 (sure they are a wolf) and a reason of at most "
            f"{REASON_MAX} characters. Keep notes to {NOTE_MAX} characters. Use only what the log "
            "shows: do not invent events, earlier days, or things people did not say. At the "
            "start of day 1 nobody has spoken yet, so a claim about someone staying quiet or "
            "acting a certain way must match a numbered line. Write like a person at the table: "
            "short, direct sentences, no speeches.",
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
    return "\n".join(lines) if lines else "Nothing yet."


def _record(view: PlayerView, from_round: int) -> str:
    """What the game wrote down about the rounds whose log is no longer shown."""
    rounds = range(1, min(from_round, view.round))
    if not rounds:
        return ""
    lines = [round_record(view.events, r) for r in rounds]
    return "## Game record (written by the game; always accurate)\n" + "\n".join(lines)


def _memory(
    view: PlayerView, beliefs: Mapping[str, Belief], summary: str, notes: Sequence[str]
) -> str:
    parts = []
    if summary:
        parts.append(f"Summary of earlier rounds: {summary}")
    known = [n for n in view.seats if n in beliefs and n != view.name and n in view.alive]
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


def _day_status(view: PlayerView) -> str:
    """A plain statement, written by the game, of what has been said today. Without it a model
    that finds nothing under "What has happened" tends to invent earlier talk."""
    today = [line for line, speech in numbered_speeches(view.events) if speech.round == view.round]
    if not today:
        if numbered_speeches(view.events):
            return "So far today: nobody has spoken."
        died = (
            f" The only thing that has happened is the death of {', '.join(view.dead)}."
            if view.dead
            else ""
        )
        return (
            f"So far today: nobody has spoken.{died} Nobody has done anything yet, so there is "
            "nothing to accuse anyone of: you may ask about the death or the table in general."
        )
    span = today[0] if len(today) == 1 else f"{today[0]} to {today[-1]}"
    return f"So far today: {_plural(len(today), 'message')} posted ({span})."


def _bid_ask(view: PlayerView, task: BidTask) -> str:
    others = ", ".join(n for n in view.alive if n != view.name)
    intents = (
        "Choose an intent (private): accuse, defend, share_info, ask, or none, and a target "
        f"from: {others} (leave the target blank if there is none)."
    )
    fields = (
        "JSON fields: bid, message, intent, target, note, beliefs, cites (a list of cited "
        "lines; [] when you cite nothing)."
    )
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
            "you must write a message; if you have nothing to say, bid 0 and leave the message "
            "and target blank (write nothing between the quotes)."
        )
    else:
        head = (
            f"Bid 0 to {task.max_bid}: bids cost nothing; 0 means you stay quiet and listen; the "
            f"highest bid speaks. Your message (at most {task.max_chars} characters) is posted "
            "only if you win the turn. If you bid above 0 you must write a message; if you have "
            "nothing to say, bid 0 and leave the message and target blank (write nothing between "
            "the quotes)."
        )
    return f"{_day_status(view)} {head} {intents} {_beliefs_ask()} {fields}"


_NO_READ = (
    "on who to kill. It is the first night: nobody has spoken or acted, so you have no read on "
    "anyone. Pick any player and say it is a guess; do not invent a reason"
)
_NO_READ_PICK = (
    "It is the first night and nobody has spoken, so any pick is a guess: no invented reasons."
)


def _task(view: PlayerView, task: Task) -> str:
    if isinstance(task, WolfChatTask):
        why = _NO_READ if view.round == 1 else "about who to kill and why"
        return (
            f"It is night. Write one private message to your partner {view.partner} (at most "
            f"{task.max_chars} characters) {why}. Only the two of you can "
            f"read it. Also write a private note (at most {NOTE_MAX} characters). "
            "JSON fields: text, note."
        )
    if isinstance(task, NightTargetTask):
        what = {
            "kill": "Choose which player the wolves kill tonight.",
            "check": "Choose one player to check tonight; you will learn their true role.",
            "protect": "Choose one player to protect tonight (you may protect yourself).",
        }[task.purpose]
        if view.round == 1:
            what += f" {_NO_READ_PICK}"
        return (
            f"{what} Options: {', '.join(task.options)}. Use an empty string for no target. "
            f"Add a private note (at most {NOTE_MAX} characters). JSON fields: target, note."
        )
    if isinstance(task, BidTask):
        return _bid_ask(view, task)
    if isinstance(task, MemoryTask):
        return (
            f"The round is over. Write a short summary (at most {task.max_chars} characters) of "
            "your own reads: who you trust and who you suspect, and why, what you noticed that "
            "is not plain fact, and what you plan to do next. The game keeps the facts (who died, "
            "how people voted, role claims) in its record, so do not copy them. It replaces your "
            "earlier summary, so keep what is still important. JSON fields: summary."
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
    persona: str = "",
    beliefs: Mapping[str, Belief] | None = None,
    summary: str = "",
    notes: Sequence[str] = (),
    from_round: int = 1,
) -> list[dict[str, str]]:
    dead = ", ".join(view.dead) or "nobody"
    now = f"Round {view.round}. Alive: {', '.join(view.alive)}. Dead: {dead}.\n{_task(view, task)}"
    if card and not isinstance(task, MemoryTask):  # said again at the moment of choosing
        now += f"\nYour strategy, keep to it: {card}"
    if view.partner and isinstance(task, BidTask):
        now += (
            "\nReminder: you are a Werewolf. The village must never learn what the wolf chat says."
        )
    if task.error:
        now += f"\n\nYour last answer was rejected: {task.error}. Answer again and fix that."
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
