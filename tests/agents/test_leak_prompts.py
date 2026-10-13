"""The prompt-level leak test (DESIGN 5.4): plant code words in every private field of a played
game, then check where they end up. Runs in CI, so the build fails if a secret reaches a prompt
it should not."""

import re

import pytest
from test_llm_agent import Rig

from werewolf.audit import find_leaks
from werewolf.engine.log import GameLog
from werewolf.engine.roles import Role
from werewolf.engine.state import Settings, SpeakingMode

SEEDS = [1, 2, 3, 4, 5, 6]


Played = dict[tuple[int, SpeakingMode], tuple[Rig, GameLog]]


@pytest.fixture(scope="module")
def games(tmp_path_factory: pytest.TempPathFactory) -> Played:
    """Every seed in every speaking mode, each played once and shared by all the tests below."""
    played: Played = {}
    for seed in SEEDS:
        for mode in SpeakingMode:
            rig = Rig(tmp_path_factory.mktemp(f"game-{seed}-{mode}"))
            rig.model.plant = True
            rig.model.kill_last = True
            played[(seed, mode)] = (
                rig,
                rig.play(seed=seed, settings=Settings(speaking_mode=mode), summarize=True),
            )
    return played


def per_player_text(rig: Rig) -> dict[str, str]:
    texts: dict[str, str] = {}
    for name, messages in rig.prompts:
        texts[name] = texts.get(name, "") + "\n".join(m["content"] for m in messages) + "\n"
    return texts


def wolves_of(log: GameLog) -> set[str]:
    return {p.name for p in log.players if p.role is Role.WEREWOLF}


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_the_wolf_chat_reaches_only_the_wolves(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, log = games[(seed, mode)]
    for name, text in per_player_text(rig).items():
        if "SECRET-WOLFCHAT-" in text:
            assert name in wolves_of(log), name


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_private_notes_reach_no_prompt_at_all(games: Played, seed: int, mode: SpeakingMode) -> None:
    rig, _ = games[(seed, mode)]
    assert all("SECRET-NOTE-" not in text for text in per_player_text(rig).values())


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_belief_reasons_reach_only_their_owner(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, _ = games[(seed, mode)]
    for name, text in per_player_text(rig).items():
        owners = set(re.findall(r"SECRET-BELIEF-(\w+)-\w+", text))
        assert owners <= {name}, (name, owners)


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_seer_results_reach_only_the_seer(games: Played, seed: int, mode: SpeakingMode) -> None:
    rig, log = games[(seed, mode)]
    seer = next(p.name for p in log.players if p.role is Role.SEER)
    for name, text in per_player_text(rig).items():
        if "You checked" in text:
            assert name == seer, name


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_only_wolves_are_told_a_partner_and_only_the_true_one(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, log = games[(seed, mode)]
    wolves = wolves_of(log)
    for name, text in per_player_text(rig).items():
        told = set(re.findall(r"Your partner is (\w+),", text))
        assert told == ({next(iter(wolves - {name}))} if name in wolves else set()), name


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_every_prompt_names_the_players_own_true_role_and_nobody_elses(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, log = games[(seed, mode)]
    roles = {p.name: p.role for p in log.players}
    for name, messages in rig.prompts:
        assert f"you are {name}, the {roles[name].value}." in messages[0]["content"]


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_the_audit_finds_nothing_in_a_clean_game(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, log = games[(seed, mode)]
    assert find_leaks(log, rig.prompts) == []


def test_the_planted_secrets_really_do_reach_the_prompts_they_should(games: Played) -> None:
    """Guards against a test that passes only because nothing was ever planted or shown."""
    seen = {"chat": 0, "belief": 0, "seer": 0, "partner": 0}
    for seed in SEEDS:
        rig, log = games[(seed, SpeakingMode.FLOOR_TOKENS)]
        for name, text in per_player_text(rig).items():
            seen["chat"] += name in wolves_of(log) and "SECRET-WOLFCHAT-" in text
            seen["belief"] += f"SECRET-BELIEF-{name}-" in text
            seen["seer"] += "You checked" in text
            seen["partner"] += "Your partner is" in text
    assert all(count > 0 for count in seen.values()), seen


@pytest.mark.parametrize("mode", list(SpeakingMode))
@pytest.mark.parametrize("seed", SEEDS)
def test_round_summaries_reach_only_their_owner(
    games: Played, seed: int, mode: SpeakingMode
) -> None:
    rig, _ = games[(seed, mode)]
    for name, text in per_player_text(rig).items():
        owners = set(re.findall(r"SECRET-SUMMARY-(\w+)-\d+", text))
        assert owners <= {name}, (name, owners)


def test_summaries_really_are_asked_for_and_shown_to_their_owner(games: Played) -> None:
    asked = shown = 0
    for seed in SEEDS:
        rig, log = games[(seed, SpeakingMode.FLOOR_TOKENS)]
        asked += sum(c.task["kind"] == "memory" for c in log.calls)
        shown += sum(
            f"Summary of earlier rounds: SECRET-SUMMARY-{name}-" in text
            for name, text in per_player_text(rig).items()
        )
    assert asked > 0 and shown > 0, (asked, shown)
