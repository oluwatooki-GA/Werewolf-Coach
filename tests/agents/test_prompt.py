"""Seed 1 seats: Di Seer, Gus, Bo, Fay (wolf), Hal (wolf), Ada Doctor, Eve, Cy."""

import json
import re

from werewolf.agents.prompt import EXAMPLES, QUIET_BID_EXAMPLE, build_messages, estimate_tokens
from werewolf.agents.wire import WIRE_FOR, json_schema_for
from werewolf.engine.actions import (
    Belief,
    BidTask,
    NightTargetTask,
    Task,
    VoteTask,
    WolfChatTask,
)
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
from werewolf.engine.roles import Role, Team
from werewolf.engine.setup import new_game
from werewolf.engine.state import GameState, Settings, SpeakingMode
from werewolf.engine.views import make_view

BID = BidTask(max_bid=3, max_chars=300)


def state_with(*events: Event, settings: Settings | None = None) -> GameState:
    state = new_game(seed=1, settings=settings)
    state.events.extend(events)
    return state


def build(
    state: GameState,
    who: str = "Cy",
    task: Task = BID,
    card: str = "",
    beliefs: dict[str, Belief] | None = None,
    summary: str = "",
    from_round: int = 1,
) -> list[dict[str, str]]:
    return build_messages(
        make_view(state, who),
        task,
        card=card,
        beliefs=beliefs,
        summary=summary,
        from_round=from_round,
    )


def system(state: GameState, who: str = "Cy", card: str = "") -> str:
    return build(state, who, card=card)[0]["content"]


def user(state: GameState, who: str = "Cy", task: Task = BID, **kw: str) -> str:
    return build(state, who, task, **kw)[1]["content"]


def happened(text: str) -> str:
    """The 'what has happened' section of a user message."""
    start = text.index("## What has happened")
    return text[start : text.index("## Your private memory")]


# --- layout ---------------------------------------------------------------------------------


def test_there_are_two_messages_a_fixed_system_one_then_the_changing_one() -> None:
    messages = build(state_with())
    assert [m["role"] for m in messages] == ["system", "user"]


def test_the_user_message_goes_log_then_memory_then_task() -> None:
    text = user(state_with(Death(round=1, player="Gus")))
    log, memory, now = (text.index(h) for h in (
        "## What has happened", "## Your private memory", "## Now",
    ))  # fmt: skip
    assert log < memory < now


def test_the_system_message_never_changes_for_a_player_during_a_game() -> None:
    quiet = state_with()
    busy = state_with(
        Death(round=1, player="Gus"), Speech(round=1, speaker="Bo", text="hi", paid=1)
    )
    busy.round = 3
    baseline = system(quiet)
    for task in (BID, VoteTask(options=("Bo",)), BidTask(max_bid=0, max_chars=300, free=True)):
        assert build(busy, task=task)[0]["content"] == baseline
    assert (
        build(busy, beliefs={"Bo": Belief(suspicion=0.9, reason="x")}, summary="s")[0]["content"]
        == baseline
    )


def test_a_later_prompt_in_the_same_round_starts_with_the_earlier_log() -> None:
    first = [
        Death(round=1, player="Gus"),
        Speech(round=1, speaker="Bo", text="Hello all", paid=2),
        Listening(round=1, player="Cy"),
        Listening(round=1, player="Di"),
    ]
    second = [
        *first,
        Speech(round=1, speaker="Eve", text="Hi Bo", paid=1),
        Listening(round=1, player="Cy"),
    ]
    a = happened(user(state_with(*first)))
    b = happened(user(state_with(*second)))
    body_a = a.split("\n", 1)[1].rstrip()
    assert b.split("\n", 1)[1].startswith(body_a)


def test_the_same_inputs_give_the_same_prompt() -> None:
    state = state_with(Death(round=1, player="Gus"))
    assert build(state) == build(state)


# --- the system message: rules, role, card -----------------------------------------------------


def test_it_names_the_player_the_role_and_the_whole_table() -> None:
    text = system(state_with(), "Cy")
    assert "You are Cy" in text and "Villager" in text
    for name in ("Di", "Gus", "Bo", "Fay", "Hal", "Ada", "Eve"):
        assert name in text


def test_a_wolf_is_told_its_partner_and_nobody_else_is() -> None:
    state = state_with()
    assert "Hal" in system(state, "Fay") and "partner" in system(state, "Fay").lower()
    assert "partner" not in system(state, "Cy").lower()


def test_each_role_is_told_what_it_can_do_at_night() -> None:
    state = state_with()
    assert "check" in system(state, "Di").lower() and "Seer" in system(state, "Di")
    assert "protect" in system(state, "Ada").lower() and "Doctor" in system(state, "Ada")
    assert "no night power" in system(state, "Cy").lower()


def test_the_rules_state_the_numbers_of_this_game() -> None:
    text = system(state_with(settings=Settings(tokens_per_day=3, speaking_turns=8, max_rounds=6)))
    assert "3 floor tokens" in text and "8 speaking turns" in text and "6 rounds" in text
    assert "300 characters" in text


def test_the_rules_follow_the_speaking_mode() -> None:
    floor = system(state_with(settings=Settings(speaking_mode=SpeakingMode.FLOOR_TOKENS)))
    free = system(state_with(settings=Settings(speaking_mode=SpeakingMode.FREE_BID)))
    fixed = system(state_with(settings=Settings(speaking_mode=SpeakingMode.FIXED_ORDER)))
    assert "floor token" in floor.lower() and "free reply" in floor.lower()
    assert "0 to 4" in free and "floor token" not in free.lower()
    assert "seat order" in fixed.lower() and "floor token" not in fixed.lower()


def test_the_strategy_card_comes_after_the_role_and_a_default_is_used_when_empty() -> None:
    with_card = system(state_with(), card="Stay quiet and watch.")
    assert with_card.index("Villager") < with_card.index("Stay quiet and watch.")
    assert "play to win" in system(state_with(), card="").lower()


def test_it_says_to_answer_only_with_the_json_asked_for() -> None:
    assert "json" in system(state_with()).lower()


# --- events in plain words ------------------------------------------------------------------


def test_events_are_written_in_plain_words() -> None:
    state = state_with(
        Death(round=1, player="Gus"),
        Speech(round=1, speaker="Bo", text="I suspect Eve.", paid=2),
        Speech(round=1, speaker="Eve", text="Not me!", paid=0, reply=True),
        Speech(round=1, speaker="Ada", text="Hmm.", paid=0),
        VoteCast(round=1, voter="Bo", target="Eve", reason="she dodged"),
        VoteCast(round=1, voter="Ada", target=None, reason=""),
        Removal(round=1, player="Eve"),
    )
    text = happened(user(state))
    assert "Gus was killed in the night" in text
    assert "Bo says (2 tokens): I suspect Eve." in text
    assert "Eve replies (free): Not me!" in text
    assert "Ada says: Hmm." in text
    assert "Bo voted for Eve (reason: she dodged)" in text
    assert "Ada abstained" in text
    assert "Eve was removed by the vote" in text


def test_a_quiet_night_and_a_no_removal_vote_are_written_out() -> None:
    text = happened(user(state_with(NoDeath(round=1), NoRemoval(round=1))))
    assert "nobody died in the night" in text.lower()
    assert "nobody was removed by the vote" in text.lower()


def test_the_end_of_the_game_is_written_out() -> None:
    text = happened(user(state_with(GameOver(round=2, winner=Team.VILLAGE))))
    assert "Village wins" in text


def test_players_who_stay_quiet_in_a_turn_are_shown_on_one_line() -> None:
    state = state_with(
        Speech(round=1, speaker="Bo", text="Hi", paid=1),
        Listening(round=1, player="Cy"),
        Listening(round=1, player="Di"),
        Listening(round=1, player="Eve"),
        Speech(round=1, speaker="Di", text="Yo", paid=1),
        Listening(round=1, player="Cy"),
    )
    text = happened(user(state))
    assert "Listening: Cy, Di, Eve" in text and "Listening: Cy" in text
    assert text.count("is listening") == 0


def test_a_new_round_starts_with_a_header() -> None:
    text = happened(user(state_with(Death(round=1, player="Gus"), Death(round=2, player="Bo"))))
    assert text.index("Round 1") < text.index("Gus") < text.index("Round 2") < text.index("Bo was")


def test_older_rounds_can_be_left_out_when_a_summary_covers_them() -> None:
    state = state_with(Death(round=1, player="Gus"), Death(round=2, player="Bo"))
    text = happened(build(state, from_round=2)[1]["content"])
    assert "Gus was killed" not in text and "Bo was killed" in text


def test_private_events_are_shown_only_to_the_players_who_may_see_them() -> None:
    state = state_with(
        WolfChat(round=1, speaker="Hal", text="Take Bo", audience=("Fay", "Hal")),
        SeerResult(round=1, target="Fay", role=Role.WEREWOLF, audience=("Di",)),
    )
    assert "Take Bo" in happened(user(state, "Fay"))
    assert "private" in happened(user(state, "Fay")).lower()
    assert "Take Bo" not in happened(user(state, "Cy"))
    assert "You checked Fay: they are a Werewolf" in happened(user(state, "Di"))
    assert "checked" not in happened(user(state, "Cy"))


def test_the_hidden_night_summary_never_appears() -> None:
    state = state_with(
        NightSummary(round=1, kill="Gus", protect=None, check="Fay", saved=False, audience=())
    )
    for name in ("Cy", "Fay", "Di", "Ada"):
        assert "Gus" not in happened(user(state, name))


def test_the_dead_are_listed_by_name_with_no_roles() -> None:
    state = state_with()
    state.players[1].alive = False  # Gus
    text = user(state)
    assert "Dead: Gus" in text
    assert "Gus (" not in text and "Gus was a" not in text


# --- memory ----------------------------------------------------------------------------------


def test_the_summary_and_beliefs_go_in_the_memory_section_in_seat_order() -> None:
    beliefs = {
        "Eve": Belief(suspicion=0.9, reason="dodged"),
        "Bo": Belief(suspicion=0.2, reason="open"),
    }
    text = user(state_with(), beliefs=beliefs, summary="Round 1: Gus died.")
    memory = text[text.index("## Your private memory") : text.index("## Now")]
    assert "Round 1: Gus died." in memory
    assert memory.index("Bo: 0.2 (open)") < memory.index(
        "Eve: 0.9 (dodged)"
    )  # seat order, not insertion


def test_with_nothing_remembered_the_memory_section_says_so() -> None:
    text = user(state_with())
    memory = text[text.index("## Your private memory") : text.index("## Now")]
    assert "nothing yet" in memory.lower()


# --- the task ---------------------------------------------------------------------------------


def test_a_floor_token_bid_explains_the_choices_and_the_limit() -> None:
    text = user(state_with(), task=BidTask(max_bid=2, max_chars=300))
    assert "2 floor tokens" in text
    assert "0 means" in text and "listen" in text.lower()
    assert "300 characters" in text
    for intent in ("accuse", "defend", "share_info", "ask"):
        assert intent in text


def test_a_free_bid_task_allows_four_and_a_fixed_order_turn_asks_for_a_message() -> None:
    free = user(
        state_with(settings=Settings(speaking_mode=SpeakingMode.FREE_BID)),
        task=BidTask(max_bid=4, max_chars=300),
    )
    assert "0 to 4" in free and "cost nothing" in free
    turn = user(state_with(), task=BidTask(max_bid=0, max_chars=300, free=True))
    assert "your turn to speak" in turn.lower() and "bid 0" in turn.lower()


def test_a_reply_task_says_who_accused_you() -> None:
    text = user(state_with(), task=BidTask(max_bid=0, max_chars=300, free=True, reply_to="Bo"))
    assert "Bo accused you" in text and "free reply" in text.lower()


def test_night_tasks_list_the_options() -> None:
    options = ("Ada", "Bo", "Cy")
    kill = user(state_with(), "Fay", NightTargetTask(purpose="kill", options=options))
    assert "kill" in kill.lower() and "Options: Ada, Bo, Cy" in kill and "empty string" in kill
    check = user(state_with(), "Di", NightTargetTask(purpose="check", options=options))
    assert "check" in check.lower()
    protect = user(state_with(), "Ada", NightTargetTask(purpose="protect", options=options))
    assert "protect" in protect.lower()


def test_a_wolf_chat_task_names_the_partner() -> None:
    text = user(state_with(), "Fay", WolfChatTask(max_chars=300))
    assert "Hal" in text and "300 characters" in text


def test_a_vote_task_lists_options_and_allows_abstaining() -> None:
    text = user(state_with(), task=VoteTask(options=("Bo", "Eve")))
    assert "Options: Bo, Eve" in text and "abstain" in text.lower()


def test_the_answer_caps_are_stated() -> None:
    text = user(state_with())
    assert "100 characters" in text and "40 characters" in text


def test_the_alive_list_and_round_are_in_the_task_section() -> None:
    state = state_with()
    state.round = 3
    now = user(state)[user(state).index("## Now") :]
    assert "Round 3" in now and "Alive: Di, Gus, Bo, Fay, Hal, Ada, Eve, Cy" in now


def test_a_retry_adds_the_error_at_the_very_end_and_nothing_otherwise() -> None:
    state = state_with()
    clean = user(state)
    retry = user(state, task=BID.model_copy(update={"error": "you can bid at most 1"}))
    assert "rejected" not in clean.lower()
    assert retry.rstrip().endswith("you can bid at most 1. Answer again and fix that.")
    assert retry.startswith(clean.split("## Now")[0])


# --- size -------------------------------------------------------------------------------------


def test_a_full_round_one_prompt_stays_under_three_thousand_tokens() -> None:
    events: list[Event] = [Death(round=1, player="Gus")]
    for turn in range(8):
        speaker = ["Bo", "Eve", "Fay", "Hal", "Ada", "Di", "Cy", "Bo"][turn]
        events.append(Speech(round=1, speaker=speaker, text="x" * 300, paid=1))
        events += [Listening(round=1, player=n) for n in ("Cy", "Di", "Eve", "Ada")]
    events += [VoteCast(round=1, voter=n, target="Eve", reason="r" * 150) for n in ("Bo", "Cy")]
    beliefs = {
        n: Belief(suspicion=0.5, reason="r" * 40) for n in ("Di", "Bo", "Fay", "Hal", "Ada", "Eve")
    }
    messages = build(state_with(*events), beliefs=beliefs, summary="s" * 800)
    assert estimate_tokens(messages) < 3000


# --- clearer rules, answer examples, and a prompt long enough to be cached ----------------------


def test_a_bid_above_zero_must_come_with_a_message_and_the_task_says_so() -> None:
    text = user(state_with(), task=BidTask(max_bid=3, max_chars=300))
    assert "must write a message" in text and "nothing to say, bid 0" in text


def test_with_no_tokens_left_the_task_says_you_cannot_speak() -> None:
    text = user(state_with(), task=BidTask(max_bid=0, max_chars=300))
    assert "no floor tokens left" in text and "bid 0" in text
    assert "Bid 0 to 0" not in text


def test_the_vote_task_says_who_you_cannot_vote_for() -> None:
    text = user(state_with(), task=VoteTask(options=("Bo", "Eve")))
    assert "cannot vote for yourself or for a dead player" in text


def test_there_is_a_valid_example_for_every_kind_of_question() -> None:
    assert set(EXAMPLES) == set(WIRE_FOR)
    for kind, example in EXAMPLES.items():
        WIRE_FOR[kind].model_validate_json(example)  # raises if an example would not be accepted
        assert example in system(state_with())


def test_the_quiet_example_is_a_valid_bid_of_zero_with_an_empty_message() -> None:
    quiet = WIRE_FOR["bid"].model_validate_json(QUIET_BID_EXAMPLE)
    assert (quiet.bid, quiet.message) == (0, "") and QUIET_BID_EXAMPLE in system(state_with())


def test_the_examples_name_no_real_player_and_give_no_strategy() -> None:
    text = " ".join([*EXAMPLES.values(), QUIET_BID_EXAMPLE])
    for name in ("Di", "Gus", "Bo", "Fay", "Hal", "Ada", "Eve", "Cy"):
        assert not re.search(rf"\b{name}\b", text), name
    for word in ("wolves rarely", "lie low", "should accuse", "best strategy"):
        assert word not in system(state_with()).lower()


def test_the_constant_part_of_the_prompt_is_long_enough_for_the_providers_cache() -> None:
    # OpenAI only caches a prefix of 1,024 tokens or more. The system message and the answer
    # schema together must clear that, with room to spare (a rough count: characters / 4).
    schema_tokens = len(json.dumps(json_schema_for("bid"), separators=(",", ":"))) // 4
    system_tokens = estimate_tokens([build(state_with())[0]])
    assert system_tokens + schema_tokens >= 1100


# --- the optional private notes -------------------------------------------------------------


def memory_section(text: str) -> str:
    return text[text.index("## Your private memory") : text.index("## Now")]


def test_recent_private_notes_are_shown_oldest_first_in_the_memory_section() -> None:
    text = build_messages(
        make_view(state_with(), "Cy"), BID, notes=["Bo went quiet", "Eve changed her story"]
    )[1]["content"]
    memory = memory_section(text)
    assert "Your recent private notes" in memory
    assert memory.index("Bo went quiet") < memory.index("Eve changed her story")


def test_without_notes_the_prompt_is_exactly_as_before() -> None:
    state = state_with(Death(round=1, player="Gus"))
    assert build(state) == build_messages(make_view(state, "Cy"), BID, notes=[])
    assert "private notes" not in memory_section(user(state)).lower()


def test_notes_alone_are_enough_to_leave_the_nothing_yet_message() -> None:
    text = build_messages(make_view(state_with(), "Cy"), BID, notes=["a thought"])[1]["content"]
    assert "Nothing yet" not in memory_section(text)
