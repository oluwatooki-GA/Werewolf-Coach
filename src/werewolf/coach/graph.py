"""One coach generation as a LangGraph: read, diagnose, write and check, test, decide, record.

The steps are plain functions in the other coach modules; this file only connects them and is the
only place LangGraph is used. A generation that is already saved is returned as it is and never
played again. A run stopped by a cap or a rate limit saves nothing for the generation, so running
again redoes it: the paid coach calls come back from the model cache, the games are played again.
"""

import asyncio
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from werewolf.coach.arena import Arm, Verdict, decide, play_arm
from werewolf.coach.check import CheckOutcome, write_checked_card
from werewolf.coach.evidence import Evidence, build_evidence
from werewolf.coach.history import (
    COACH_DIR,
    ArmResult,
    CheckSummary,
    Generation,
    load_history,
    save_generation,
)
from werewolf.coach.steps import CoachError, CoachStopped, Diagnosis, diagnose
from werewolf.engine.log import GameLog
from werewolf.engine.state import Settings
from werewolf.llm.client import LLMClient
from werewolf.strategies.cards import (
    CARDS_DIR,
    COACH_FOLDER,
    Card,
    load_card,
    read_card,
    write_card,
)
from werewolf.tagger.tags import TagFile


class State(TypedDict, total=False):
    evidence: Evidence
    diagnosis: Diagnosis
    outcome: CheckOutcome
    champion_arm: Arm
    challenger_arm: Arm
    verdict: Verdict
    generation: Generation


def _result(arm: Arm, ref: str) -> ArmResult:
    return ArmResult(
        card=ref, seeds=arm.seeds, wins=arm.wins, games=arm.games, clean=arm.clean,
        cost=arm.cost, stopped=arm.stopped,
    )  # fmt: skip


def _keep_card(card: Card) -> None:
    """Put the card where the game runner finds it. Writing it again after a crash is fine if it
    is the same card; a different card under the same id is an error."""
    path = CARDS_DIR / COACH_FOLDER / f"{card.id}.yaml"
    if not path.exists():
        write_card(card)
    elif read_card(path) != card:
        raise CoachError(f"{path.name} already holds a different card; use another run tag")


def _seen(evidence: Evidence) -> str:
    text = f"{evidence.used} of {evidence.lost} lost games, out of {evidence.games} played"
    return text + (f" ({evidence.left_out} left out)" if evidence.left_out else "")


async def run_generation(
    client: LLMClient,
    *,
    side: str,
    number: int,
    champion: str,
    games: Sequence[tuple[GameLog, TagFile | None]],
    seeds: list[int],
    player_model: str,
    coach_model: str,
    check_model: str,
    settings: Settings,
    data_dir: Path,
    root: Path = COACH_DIR,
    run: str = "",
    parallel: int = 3,
    player_client: LLMClient | None = None,
) -> Generation:
    """Run generation `number` of one side's coach and return it, saved. `champion` is the id of
    the card to beat; `games` are the earlier games the coach reads."""
    saved = load_history(side, root)
    if number <= len(saved):
        return saved[number - 1]
    if number != len(saved) + 1:
        raise ValueError(f"generation {number} cannot run: {len(saved)} are finished")
    champion_card = load_card(champion)
    coach_cost = Decimal("0")

    async def read(state: State) -> State:
        return {"evidence": build_evidence(games, side, champion_card.id)}

    async def think(state: State) -> State:
        nonlocal coach_cost
        diagnosis, cost = await diagnose(client, coach_model, state["evidence"], champion_card)
        coach_cost += cost
        return {"diagnosis": diagnosis}

    async def write(state: State) -> State:
        nonlocal coach_cost
        try:
            outcome = await write_checked_card(
                client, coach_model, check_model, side, number, state["diagnosis"], champion_card,
                run=run,
            )  # fmt: skip
        except CoachError as exc:
            coach_cost += exc.cost
            raise
        coach_cost += outcome.cost
        if outcome.card:
            _keep_card(outcome.card)
        return {"outcome": outcome}

    def after_write(state: State) -> str:
        return "test" if state["outcome"].card else "record"

    async def test(state: State) -> State:
        card = state["outcome"].card
        assert card is not None
        arms = await asyncio.gather(
            *(
                play_arm(
                    player_client or client,
                    player_model,
                    side,
                    c.id,
                    seeds,
                    settings=settings,
                    data_dir=data_dir,
                    parallel=parallel,
                )  # fmt: skip
                for c in (champion_card, card)
            )
        )
        for arm in arms:
            if arm.stopped:
                raise CoachStopped(f"games for {arm.card} stopped early: {arm.stopped}")
        return {"champion_arm": arms[0], "challenger_arm": arms[1]}

    async def judge(state: State) -> State:
        return {"verdict": decide(state["champion_arm"], state["challenger_arm"])}

    async def record(state: State) -> State:
        outcome, diagnosis = state["outcome"], state["diagnosis"]
        card, verdict = outcome.card, state.get("verdict")
        promote = bool(verdict and verdict.promote)
        arms = (state.get("champion_arm"), state.get("challenger_arm"))
        generation = Generation(
            side=side,
            number=number,
            champion_before=champion_card.ref,
            champion_after=card.ref if card and promote else champion_card.ref,
            evidence=_seen(state["evidence"]),
            diagnosis=diagnosis.text,
            challenger_card=card.ref if card else None,
            challenger_text=f"{card.summary}\n{card.prompt_text}" if card else "",
            check=CheckSummary(
                attempts=outcome.attempts, passed=card is not None, reasons=outcome.reasons
            ),
            champion_arm=_result(arms[0], champion_card.ref) if arms[0] else None,
            challenger_arm=_result(arms[1], card.ref) if arms[1] and card else None,
            promote=promote,
            decision=verdict.reason if verdict else "no card passed its checks, so none was played",
            coach_cost=coach_cost,
        )
        save_generation(generation, root)
        return {"generation": generation}

    graph = StateGraph(State)
    for name, node in (
        ("read", read), ("diagnose", think), ("write", write), ("test", test),
        ("decide", judge), ("record", record),
    ):  # fmt: skip
        graph.add_node(name, node)
    graph.add_edge(START, "read")
    graph.add_edge("read", "diagnose")
    graph.add_edge("diagnose", "write")
    graph.add_conditional_edges("write", after_write, {"test": "test", "record": "record"})
    graph.add_edge("test", "decide")
    graph.add_edge("decide", "record")
    graph.add_edge("record", END)
    final = await graph.compile().ainvoke({})
    generation: Generation = final["generation"]
    return generation
