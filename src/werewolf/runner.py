"""Run model-driven games, one or many at a time, and report what happened."""

import asyncio
import hashlib
import json
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from werewolf.agents import persona as personas
from werewolf.agents.leakguard import REWRITE
from werewolf.agents.llm_agent import LLMAgent
from werewolf.audit import Leak, find_leaks
from werewolf.engine.actions import FatalAgentError
from werewolf.engine.events import Speech
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import CallRecord, Settings, SpeakingMode
from werewolf.llm.client import LLMClient
from werewolf.strategies.cards import assign_cards, load_card
from werewolf.tagger.grounding import GroundStopped, check_game

CacheMode = Literal["fresh", "shared"]


@dataclass
class Played:
    seed: int
    run_id: str
    log: GameLog
    seconds: float
    leaks: list[Leak]
    path: Path
    rewrites: int = 0  # wolf messages sent back once for giving away the wolf chat
    claims: tuple[int, int, int] | None = None  # (checked, unsupported, not checkable); None: off
    claim_cost: Decimal = Decimal("0")  # what the fact-check cost; it is not in the log's stats


@dataclass
class BatchReport:
    played: list[Played] = field(default_factory=list)
    interrupted: int = 0  # games that were under way when the run had to stop
    not_started: int = 0
    stopped: str | None = None  # why the run stopped early, if it did


def save_log(log: GameLog, data_dir: Path) -> Path:
    text = log.to_json()
    path = data_dir / f"{log.seed}-{hashlib.sha256(text.encode()).hexdigest()[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # bytes, so Windows never turns \n into \r\n
    return path


async def run_batch(
    client: LLMClient,
    model: str,
    seeds: Sequence[int],
    *,
    settings: Settings,
    parallel: int,
    cache: CacheMode,
    data_dir: Path,
    announce: Callable[[Played], None] | None = None,
    keep_notes: int = 0,
    max_tokens: int = 300,
    use_personas: bool = True,
    cards_by_role: Mapping[Role, str] | None = None,
    cards_by_seat: Mapping[str, str] | None = None,
    claim_model: str | None = None,
    claim_tokens: int = 200,
) -> BatchReport:
    """Play one game per seed, `parallel` at a time. A hard stop (the spending cap) ends the
    run: games not yet started are skipped and a game under way is dropped, not saved."""
    report = BatchReport()
    gate = asyncio.Semaphore(max(1, parallel))
    # Worked out for every seed before any call is made, so a bad card stops the run for free.
    seat_cards = {
        seed: assign_cards(
            {p.name: p.role for p in new_game(seed, settings).players},
            cards_by_role or {},
            cards_by_seat or {},
        )
        for seed in seeds
    }

    async def one(seed: int) -> None:
        async with gate:
            if report.stopped is not None:
                report.not_started += 1
                return
            # A fresh run id per game is also the cache salt, so a repeated seed is a new game.
            run_id = uuid.uuid4().hex[:12]
            salt = run_id if cache == "fresh" else ""
            prompts: list[tuple[str, list[dict[str, str]]]] = []
            seat_persona = personas.assign(seed, settings.names) if use_personas else {}
            game_settings = settings.model_copy(
                update={"personas": seat_persona, "cards": seat_cards[seed]}
            )

            def record(name: str, messages: list[dict[str, str]]) -> None:
                prompts.append((name, messages))

            agents = {
                p.name: LLMAgent(
                    p.name,
                    client,
                    model,
                    cache_salt=salt,
                    game_id=run_id if cache == "fresh" else f"seed{seed}",
                    summarize=settings.summarize_rounds,
                    keep_notes=keep_notes,
                    persona=seat_persona.get(p.name, ""),
                    card=load_card(seat_cards[seed][p.name]).prompt_text
                    if p.name in seat_cards[seed]
                    else "",
                    max_tokens=max_tokens,
                    on_prompt=record,
                )
                for p in new_game(seed, game_settings).players
            }
            started = time.perf_counter()
            try:
                state = await play_game(seed, game_settings, agents)
            except FatalAgentError as exc:
                report.interrupted += 1
                report.stopped = report.stopped or str(exc)
                return
            log = to_log(state, run_id=run_id, model=model)
            claims: tuple[int, int, int] | None = None
            claim_cost = Decimal("0")
            if claim_model:
                try:
                    ground = await check_game(log, client, claim_model, max_tokens=claim_tokens)
                except GroundStopped as stop:  # keep the game; no further games are started
                    report.stopped = report.stopped or str(stop)
                    ground = stop.run
                claims = (ground.checked, len(ground.flagged), len(ground.failed))
                claim_cost = ground.cost
            played = Played(
                seed=seed,
                run_id=run_id,
                log=log,
                seconds=time.perf_counter() - started,
                leaks=find_leaks(log, prompts, own_notes_ok=keep_notes > 0),
                path=save_log(log, data_dir),
                rewrites=sum(REWRITE in messages[1]["content"] for _, messages in prompts),
                claims=claims,
                claim_cost=claim_cost,
            )
            report.played.append(played)
            if announce is not None:
                announce(played)

    await asyncio.gather(*(one(seed) for seed in seeds))
    report.played.sort(key=lambda p: p.seed)
    return report


def cite_counts(logs: Sequence[GameLog]) -> tuple[int, int, int]:
    """(messages posted, cites made, cites that were invented), added up over the games."""
    speeches = [e for log in logs for e in log.events if isinstance(e, Speech)]
    cited = sum(len(e.cites) for e in speeches)
    return len(speeches), cited, sum(len(e.invented) for e in speeches)


def cite_text(logs: Sequence[GameLog]) -> str:
    messages, cited, invented = cite_counts(logs)
    if not cited:
        return f"no cites in {messages} messages"
    rate = 100 * invented / cited
    return f"{cited} cites in {messages} messages, invented {invented} ({rate:.1f}%)"


def citing_messages(logs: Sequence[GameLog]) -> int:
    """How many posted messages carry at least one cite."""
    return sum(bool(e.cites) for log in logs for e in log.events if isinstance(e, Speech))


def _accepted_bid(call: CallRecord) -> int:
    """The bid the engine used for this call: the last answer, or 0 if it fell back."""
    if call.failed:
        return 0
    answer = call.responses[-1]
    try:
        data = json.loads(answer) if isinstance(answer, str) else answer
        return int(data["bid"])
    except (ValueError, KeyError, TypeError):
        return 0


def bid_counts(logs: Sequence[GameLog]) -> tuple[Counter[int], Counter[int]]:
    """(every bid the players chose, the bids that won the floor), counted by size. A turn with
    no tokens left, and a free reply, is not a choice, so it is left out."""
    chosen: Counter[int] = Counter()
    won: Counter[int] = Counter()
    for log in logs:
        for call in log.calls:
            task = call.task
            if task.get("kind") == "bid" and not task.get("free") and task.get("max_bid"):
                chosen[_accepted_bid(call)] += 1
        if log.settings.speaking_mode is SpeakingMode.FLOOR_TOKENS:  # only there a bid is paid
            won.update(e.paid for e in log.events if isinstance(e, Speech) and not e.reply)
    return chosen, won


def bid_text(logs: Sequence[GameLog]) -> str:
    chosen, won = bid_counts(logs)

    def sizes(counts: Counter[int]) -> str:
        return " ".join(f"{size}:{counts[size]}" for size in sorted(counts)) or "none"

    return f"bids {sizes(chosen)} (won the floor with {sizes(won)})"


def claim_text(played: Sequence[Played]) -> str:
    """Messages whose claims about earlier play the public log does not back up."""
    runs = [p.claims for p in played if p.claims is not None]
    if not runs:
        return "claims not checked"
    checked, flagged = sum(r[0] for r in runs), sum(r[1] for r in runs)
    failed = sum(r[2] for r in runs)
    rate = f" ({100 * flagged / checked:.0f}%)" if checked else ""
    more = f", {failed} could not be checked" if failed else ""
    return f"unsupported claims {flagged} of {checked} messages{rate}{more}"


def quiet_bids(logs: Sequence[GameLog]) -> int:
    """Bids above 0 that came with no message. The engine reads them as listening."""
    count = 0
    for log in logs:
        for call in log.calls:
            task = call.task
            if task.get("kind") != "bid" or task.get("free") or call.failed or not call.responses:
                continue
            try:
                answer = call.responses[-1]
                data = json.loads(answer) if isinstance(answer, str) else answer
                count += int(data["bid"]) > 0 and not str(data.get("message", "")).strip()
            except (ValueError, KeyError, TypeError):
                continue
    return count


def reject_reasons(logs: Sequence[GameLog], top: int = 5) -> str:
    """Why answers were turned down, grouped with the names and line numbers taken out."""
    counts: Counter[str] = Counter()
    for log in logs:
        names = "|".join(re.escape(n) for n in log.settings.names)
        for call in log.calls:
            for error in call.errors:
                text = re.sub(r"R\d+-\d+ \(\w+\)", "", error)
                text = re.sub(rf"\b({names})\b", "", text)
                counts[" ".join(text.replace(",", " ").split())[:60]] += 1
    return "; ".join(f"{reason} x{n}" for reason, n in counts.most_common(top)) or "none"


def format_game(p: Played) -> str:
    s = p.log.stats
    return (
        f"seed {p.seed}: {p.log.winner.value} won in {p.log.rounds} rounds, "
        f"rejected {s.rejected} of {s.responses}, cost ${s.cost + p.claim_cost:.6f}, "
        f"{p.seconds:.1f} s, "
        f"leaks {len(p.leaks)}, {cite_text([p.log])}, {claim_text([p])}, run {p.run_id}\n"
        f"  {bid_text([p.log])}\n"
        f"  saved to {p.path}\n"
        f"  read it:  uv run python -m werewolf.cli show {p.path}"
    )


def format_report(report: BatchReport) -> str:
    games = [p.log for p in report.played]
    n = len(games)
    responses = sum(g.stats.responses for g in games)
    rejected = sum(g.stats.rejected for g in games)
    prompt = sum(g.stats.prompt_tokens for g in games)
    completion = sum(g.stats.completion_tokens for g in games)
    cached = sum(g.stats.cached_tokens for g in games)
    cost = sum((g.stats.cost for g in games), Decimal("0"))
    checks = sum((p.claim_cost for p in report.played), Decimal("0"))
    winners = Counter(g.winner.value for g in games)
    leaks = [(p, leak) for p in report.played for leak in p.leaks]
    rate = 100 * rejected / responses if responses else 0.0
    share = round(100 * cached / prompt) if prompt else 0
    lines = [
        f"games: {n} finished, {report.interrupted} stopped",
        "winners: " + (", ".join(f"{w} {c}" for w, c in sorted(winners.items())) or "none"),
        f"answers: rejected {rejected} of {responses} ({rate:.1f}%), "
        f"fallbacks {sum(g.stats.failed_calls for g in games)}, "
        f"clean games {sum(g.stats.clean for g in games)} of {n}, "
        f"cut off {sum(g.stats.truncated for g in games)}",
        f"cites: {cite_text(games)}",
        f"messages that cite: {citing_messages(games)} of {cite_counts(games)[0]}",
        bid_text(games),
        f"tokens: input {prompt:,} ({share}% cached), output {completion:,}",
        f"cost: ${cost + checks:.6f} total, ${(cost + checks) / n if n else Decimal('0'):.6f} "
        f"per game (the fact-check is ${checks:.6f} of it)",
        f"time: {sum(p.seconds for p in report.played) / n if n else 0.0:.1f} s per game",
        f"rejected for: {reject_reasons(games)}",
        f"bids with no message, read as listening: {quiet_bids(games)}",
        f"wolf-chat rewrites: {sum(p.rewrites for p in report.played)}",
        claim_text(report.played),
        f"leaks: {len(leaks)}",
    ]
    lines += [
        f"LEAK seed {p.seed}: {leak.kind} in {leak.player}'s prompt: {leak.detail}"
        for p, leak in leaks
    ]
    if report.stopped is not None:
        lines.append(f"STOPPED EARLY: {report.stopped}; {report.not_started} game(s) not started")
    return "\n".join(lines)
