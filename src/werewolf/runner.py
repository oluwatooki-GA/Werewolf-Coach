"""Run model-driven games, one or many at a time, and report what happened."""

import asyncio
import hashlib
import json
import time
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from werewolf.agents import persona as personas
from werewolf.agents.llm_agent import LLMAgent
from werewolf.audit import Leak, find_leaks
from werewolf.engine.actions import FatalAgentError
from werewolf.engine.events import Speech
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, to_log
from werewolf.engine.setup import new_game
from werewolf.engine.state import CallRecord, Settings, SpeakingMode
from werewolf.llm.client import LLMClient

CacheMode = Literal["fresh", "shared"]


@dataclass
class Played:
    seed: int
    run_id: str
    log: GameLog
    seconds: float
    leaks: list[Leak]
    path: Path


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
) -> BatchReport:
    """Play one game per seed, `parallel` at a time. A hard stop (the spending cap) ends the
    run: games not yet started are skipped and a game under way is dropped, not saved."""
    report = BatchReport()
    gate = asyncio.Semaphore(max(1, parallel))

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
            game_settings = settings.model_copy(update={"personas": seat_persona})

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
            log = to_log(state, run_id=run_id)
            played = Played(
                seed=seed,
                run_id=run_id,
                log=log,
                seconds=time.perf_counter() - started,
                leaks=find_leaks(log, prompts, own_notes_ok=keep_notes > 0),
                path=save_log(log, data_dir),
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


def format_game(p: Played) -> str:
    s = p.log.stats
    return (
        f"seed {p.seed}: {p.log.winner.value} won in {p.log.rounds} rounds, "
        f"rejected {s.rejected} of {s.responses}, cost ${s.cost:.6f}, {p.seconds:.1f} s, "
        f"leaks {len(p.leaks)}, {cite_text([p.log])}, run {p.run_id}\n"
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
        f"cost: ${cost:.6f} total, ${cost / n if n else Decimal('0'):.6f} per game",
        f"time: {sum(p.seconds for p in report.played) / n if n else 0.0:.1f} s per game",
        f"leaks: {len(leaks)}",
    ]
    lines += [
        f"LEAK seed {p.seed}: {leak.kind} in {leak.player}'s prompt: {leak.detail}"
        for p, leak in leaks
    ]
    if report.stopped is not None:
        lines.append(f"STOPPED EARLY: {report.stopped}; {report.not_started} game(s) not started")
    return "\n".join(lines)
