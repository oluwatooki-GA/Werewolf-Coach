import json

from werewolf.agents.memory import PlayerMemory


def answer(**fields: object) -> str:
    return json.dumps(fields)


def test_a_new_memory_is_empty() -> None:
    m = PlayerMemory()
    assert (m.summary, m.beliefs, list(m.notes)) == ("", {}, [])


def test_beliefs_come_from_every_answer_and_the_latest_entry_for_a_player_wins() -> None:
    m = PlayerMemory()
    m.remember("bid", answer(beliefs={"Bo": {"suspicion": 0.2, "reason": "open"}}))
    m.remember(
        "vote",
        answer(
            beliefs={
                "Bo": {"suspicion": 0.9, "reason": "dodged"},
                "Cy": {"suspicion": 0.1, "reason": "calm"},
            }
        ),
    )
    assert m.beliefs["Bo"].suspicion == 0.9 and m.beliefs["Cy"].reason == "calm"


def test_a_summary_replaces_the_old_one_and_an_empty_one_keeps_it() -> None:
    m = PlayerMemory()
    m.remember("memory", answer(summary="first"))
    m.remember("memory", answer(summary="second"))
    m.remember("memory", answer(summary="   "))
    assert m.summary == "second"


def test_a_summary_only_counts_for_the_memory_question() -> None:
    m = PlayerMemory()
    m.remember("bid", answer(summary="not a summary question", beliefs={}))
    assert m.summary == ""


def test_notes_are_off_by_default() -> None:
    m = PlayerMemory()
    m.remember("bid", answer(note="a private thought", beliefs={}))
    assert list(m.notes) == []


def test_with_notes_on_it_keeps_the_last_few_oldest_first() -> None:
    m = PlayerMemory(keep_notes=3)
    for i in range(5):
        m.remember("bid", answer(note=f"thought {i}", beliefs={}))
    assert list(m.notes) == ["thought 2", "thought 3", "thought 4"]


def test_blank_notes_and_answers_without_a_note_are_not_stored() -> None:
    m = PlayerMemory(keep_notes=3)
    m.remember("bid", answer(note="   ", beliefs={}))
    m.remember("bid", answer(beliefs={}))
    m.remember("memory", answer(summary="a summary"))
    assert list(m.notes) == []
