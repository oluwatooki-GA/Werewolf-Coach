import json

import pytest
from test_llm_agent import Rig

from werewolf.audit import Leak, find_leaks
from werewolf.engine.events import SeerResult, WolfChat
from werewolf.engine.log import GameLog
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game

Prompts = list[tuple[str, list[dict[str, str]]]]


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> tuple[GameLog, Prompts]:
    rig = Rig(tmp_path_factory.mktemp("audit"))
    rig.model.plant = True
    rig.model.kill_last = True
    log = rig.play(seed=1, summarize=True)
    return log, rig.prompts


def villager(log: GameLog) -> str:
    return next(p.name for p in log.players if p.role is Role.VILLAGER)


def system_of(prompts: Prompts, name: str) -> str:
    return next(m[0]["content"] for n, m in prompts if n == name)


def with_extra(prompts: Prompts, name: str, extra: str) -> Prompts:
    """The real prompts plus one more prompt for this player that contains `extra`."""
    messages = [
        {"role": "system", "content": system_of(prompts, name)},
        {"role": "user", "content": f"## What has happened\n{extra}"},
    ]
    return [*prompts, (name, messages)]


def kinds(leaks: list[Leak]) -> set[str]:
    return {leak.kind for leak in leaks}


def test_a_clean_game_has_no_leaks(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    assert find_leaks(log, prompts) == []


def test_a_wolf_chat_line_in_a_villagers_prompt_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    secret = next(e.text for e in log.events if isinstance(e, WolfChat))
    leaks = find_leaks(log, with_extra(prompts, villager(log), f"someone said: {secret}"))
    assert kinds(leaks) == {"wolf_chat"} and leaks[0].player == villager(log)


def test_a_private_note_in_any_prompt_is_a_leak_even_the_owners(
    game: tuple[GameLog, Prompts],
) -> None:
    log, prompts = game
    note = next(
        c.responses[0] for c in log.calls if c.responses and "SECRET-NOTE-" in str(c.responses[0])
    )
    text = note.split('"note": "')[1].split('"')[0]
    owner = next(c.player for c in log.calls if text in str(c.responses))
    assert kinds(find_leaks(log, with_extra(prompts, owner, text))) == {"note"}
    assert kinds(find_leaks(log, with_extra(prompts, villager(log), text))) == {"note"}


def test_a_belief_reason_in_another_players_prompt_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    other = villager(log)
    owner = next(p.name for p in log.players if p.name != other)
    reason = f"SECRET-BELIEF-{owner}-{other}"
    assert kinds(find_leaks(log, with_extra(prompts, other, reason))) == {"belief"}
    assert find_leaks(log, with_extra(prompts, owner, reason)) == []  # its owner may see it


def test_a_seer_result_in_a_non_seers_prompt_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    result = next(e for e in log.events if isinstance(e, SeerResult))
    line = f"[Private] You checked {result.target}: they are a {result.role.value}."
    assert kinds(find_leaks(log, with_extra(prompts, villager(log), line))) == {"seer_result"}
    seer = next(p.name for p in log.players if p.role is Role.SEER)
    assert find_leaks(log, with_extra(prompts, seer, line)) == []


def test_a_partner_line_in_a_villagers_prompt_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    name = villager(log)
    messages = [
        {
            "role": "system",
            "content": system_of(prompts, name) + " Your partner is Hal, the other.",
        },
        {"role": "user", "content": "x"},
    ]
    assert kinds(find_leaks(log, [*prompts, (name, messages)])) == {"partner"}


def test_naming_the_wrong_partner_to_a_wolf_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    wolf = next(p.name for p in log.players if p.role is Role.WEREWOLF)
    wrong = next(p.name for p in log.players if p.role is Role.VILLAGER)
    text = system_of(prompts, wolf)
    right = text.split("Your partner is ")[1].split(",")[0]
    messages = [
        {
            "role": "system",
            "content": text.replace(f"Your partner is {right},", f"Your partner is {wrong},"),
        },
        {"role": "user", "content": "x"},
    ]
    assert kinds(find_leaks(log, [*prompts, (wolf, messages)])) == {"partner"}


def test_a_prompt_that_gives_a_player_the_wrong_role_is_a_leak(
    game: tuple[GameLog, Prompts],
) -> None:
    log, prompts = game
    name = villager(log)
    text = system_of(prompts, name).replace(
        f"the {Role.VILLAGER.value}.", f"the {Role.SEER.value}."
    )
    messages = [{"role": "system", "content": text}, {"role": "user", "content": "x"}]
    assert kinds(find_leaks(log, [*prompts, (name, messages)])) == {"role"}


def test_short_texts_are_ignored_to_avoid_false_alarms(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    assert find_leaks(log, with_extra(prompts, villager(log), "n")) == []


def test_no_prompts_means_no_leaks(game: tuple[GameLog, Prompts]) -> None:
    log, _ = game
    assert find_leaks(log, []) == []


def test_a_round_summary_in_another_players_prompt_is_a_leak(game: tuple[GameLog, Prompts]) -> None:
    log, prompts = game
    owner, summary = next(
        (c.player, json.loads(r)["summary"])
        for c in log.calls
        for r in c.responses
        if isinstance(r, str) and "SECRET-SUMMARY-" in r
    )
    other = next(p.name for p in log.players if p.name != owner)
    assert kinds(find_leaks(log, with_extra(prompts, other, summary))) == {"summary"}
    assert find_leaks(log, with_extra(prompts, owner, summary)) == []


def test_players_who_wrote_the_same_generic_text_are_not_flagged_for_it(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rig = Rig(tmp_path_factory.mktemp("generic"))  # every player writes "A short summary."
    log = rig.play(seed=2, summarize=True)
    summaries = {
        r for c in log.calls for r in c.responses if isinstance(r, str) and "A short summary." in r
    }
    assert summaries and any("A short summary." in m[1]["content"] for _, m in rig.prompts)
    assert find_leaks(log, rig.prompts) == []


def test_a_private_text_that_was_also_said_in_public_is_not_a_leak(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Models reuse a phrase as both a private belief reason and a public vote reason."""
    shared = "Quiet and suspicious, could be wolf"
    rig = Rig(tmp_path_factory.mktemp("public"))
    rig.model.beliefs_for["Cy"] = [{"player": "Bo", "suspicion": 0.5, "reason": shared}]
    rig.model.vote_reason_for = {p.name: shared for p in new_game(1).players}
    log = rig.play(seed=1, summarize=True)
    others = [n for n, m in rig.prompts if n != "Cy" and shared in m[1]["content"]]
    assert others  # the phrase really is in other players' prompts, as a public vote reason
    assert find_leaks(log, rig.prompts) == []


def test_a_private_text_a_player_wrote_itself_may_come_back_in_its_own_prompt(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Bo's private note happens to equal Cy's private belief reason. Cy's own memory shows its
    belief reason, so Cy's prompt holds Bo's note text, and Cy wrote that very text itself."""
    phrase = "Nervous and keeps changing the subject"
    rig = Rig(tmp_path_factory.mktemp("selfwritten"))
    rig.model.note_for["Bo"] = phrase
    rig.model.beliefs_for["Cy"] = [{"player": "Eve", "suspicion": 0.5, "reason": phrase}]
    log = rig.play(seed=1, summarize=True)
    cy_prompts = [m[1]["content"] for n, m in rig.prompts if n == "Cy"]
    assert any(phrase in text for text in cy_prompts)  # it really is in Cy's prompt
    assert find_leaks(log, rig.prompts) == []


def test_a_note_in_the_prompt_of_a_player_who_never_wrote_it_is_still_a_leak(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    phrase = "Nervous and keeps changing the subject"
    rig = Rig(tmp_path_factory.mktemp("notwritten"))
    rig.model.note_for["Bo"] = phrase
    log = rig.play(seed=1)
    other = next(p.name for p in log.players if p.name != "Bo")
    messages = [
        {"role": "system", "content": system_of(rig.prompts, other)},
        {"role": "user", "content": f"## What has happened\n{phrase}"},
    ]
    assert kinds(find_leaks(log, [*rig.prompts, (other, messages)])) == {"note"}


def own_note(log: GameLog) -> tuple[str, str]:
    """(author, text) of one planted private note."""
    for call in log.calls:
        for response in call.responses:
            if isinstance(response, str) and "SECRET-NOTE-" in response:
                return call.player, json.loads(response)["note"]
    raise AssertionError("no planted note found")


def test_with_the_scratchpad_on_a_players_own_note_may_be_in_its_own_prompt(
    game: tuple[GameLog, Prompts],
) -> None:
    log, prompts = game
    author, note = own_note(log)
    extra = with_extra(prompts, author, note)
    assert kinds(find_leaks(log, extra)) == {"note"}  # by default notes go to nobody
    assert find_leaks(log, extra, own_notes_ok=True) == []


def test_even_with_the_scratchpad_on_a_note_in_someone_elses_prompt_is_a_leak(
    game: tuple[GameLog, Prompts],
) -> None:
    log, prompts = game
    author, note = own_note(log)
    other = next(p.name for p in log.players if p.name != author)
    leaks = find_leaks(log, with_extra(prompts, other, note), own_notes_ok=True)
    assert kinds(leaks) == {"note"} and leaks[0].player == other


def test_a_note_copied_from_the_answer_examples_is_not_a_leak(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Models copy the example note word for word; that text is in every system message."""
    copied = "Nothing to add yet."
    rig = Rig(tmp_path_factory.mktemp("example"))
    rig.model.note_for["Bo"] = copied
    log = rig.play(seed=1)
    assert all(copied in m[0]["content"] for _, m in rig.prompts)  # it is in the system message
    assert find_leaks(log, rig.prompts) == []


def test_a_phrase_inside_the_players_own_note_is_not_a_leak_when_it_sees_its_notes(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Bo's belief reason is a short generic phrase; Cy's own note contains it. With the
    scratchpad on, Cy sees its own notes, so the phrase comes back through text Cy wrote."""
    phrase = "has not spoken yet at all"
    rig = Rig(tmp_path_factory.mktemp("insidenote"))
    rig.model.beliefs_for["Bo"] = [{"player": "Eve", "suspicion": 0.5, "reason": phrase}]
    rig.model.note_for["Cy"] = f"Gus {phrase}, odd"
    log = rig.play(seed=1, keep_notes=2)
    assert any(
        phrase in m[1]["content"] or phrase in m[-2]["content"] for n, m in rig.prompts if n == "Cy"
    )
    assert find_leaks(log, rig.prompts, own_notes_ok=True) == []
    assert "belief" in kinds(find_leaks(log, rig.prompts))  # with notes hidden it is a leak
