"""Command line: play one scripted game and save its log, or replay a saved log.

uv run python -m werewolf.cli play --seed 1 --agents scripted
uv run python -m werewolf.cli replay data/games/<id>.json
"""

import argparse
import asyncio
import hashlib
import io
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from werewolf.agents.scripted import policy
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replay, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings, SpeakingMode


def _bounded(low: int, high: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        number = int(text)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be from {low} to {high}")
        return number

    return parse


def _add_game_options(parser: argparse.ArgumentParser) -> None:
    """How long the talking is: both commands that play games take these."""
    defaults = Settings()
    parser.add_argument(
        "--turns",
        type=_bounded(1, 40),
        default=defaults.speaking_turns,
        help="speaking turns per day, at most (default: %(default)s)",
    )
    parser.add_argument(
        "--tokens-per-day",
        type=_bounded(1, 10),
        default=defaults.tokens_per_day,
        help="floor tokens each player gets a day; they limit how often one can speak "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--message-chars",
        type=_bounded(50, 2000),
        default=defaults.max_message_chars,
        help="longest message, in characters (default: %(default)s)",
    )


def _settings(args: argparse.Namespace, **more: bool) -> Settings:
    return Settings(
        speaking_mode=SpeakingMode(args.speaking_mode),
        speaking_turns=args.turns,
        tokens_per_day=args.tokens_per_day,
        max_message_chars=args.message_chars,
        **more,
    )


def _llm(args: argparse.Namespace, seeds: list[int]) -> int:
    """Play model-driven games and print the report. Exit 1 if the run stopped or leaked."""
    from decimal import Decimal

    from werewolf import runner, runtime

    if not args.model:
        print("--model is required with --agents llm", file=sys.stderr)
        return 2
    spend = Decimal(args.max_spend) if args.max_spend is not None else None
    try:
        client = runtime.build_client(args.model, spend, requests_per_minute=args.rpm)
    except RuntimeError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    settings = _settings(args, summarize_rounds=True)
    report = asyncio.run(
        runner.run_batch(
            client,
            args.model,
            seeds,
            settings=settings,
            parallel=getattr(args, "parallel", 1),
            cache=args.cache,
            data_dir=Path(args.data_dir),
            announce=lambda played: print(runner.format_game(played), flush=True),
            keep_notes=args.notes,
            use_personas=args.persona,
            max_tokens=args.max_tokens
            or runtime.default_max_tokens(args.model, args.message_chars),
        )
    )
    print(runner.format_report(report))
    return 1 if report.stopped is not None or any(p.leaks for p in report.played) else 0


def _batch(args: argparse.Namespace) -> int:
    return _llm(args, list(range(args.first_seed, args.first_seed + args.games)))


def _play(args: argparse.Namespace) -> int:
    if args.agents == "llm":
        return _llm(args, [args.seed])
    settings = _settings(args)
    players = new_game(args.seed, settings).players
    wolves = [p.name for p in players if p.role is Role.WEREWOLF]
    agents = {p.name: policy(wolves) for p in players}  # "scripted" is the only kind in M1
    log = to_log(asyncio.run(play_game(args.seed, settings, agents)))

    text = log.to_json()
    path = Path(args.data_dir) / f"{args.seed}-{hashlib.sha256(text.encode()).hexdigest()[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # bytes, so Windows never turns \n into \r\n

    s = log.stats
    rate = s.rejected / s.responses if s.responses else 0.0
    print(f"{log.winner.value} won in {log.rounds} rounds")
    print(f"answers: rejected {s.rejected} of {s.responses} ({rate:.1%}), "
          f"fallbacks: {s.failed_calls}, clean: {'yes' if s.clean else 'no'}")  # fmt: skip
    print(f"saved to {path}")
    return 0


def _show(args: argparse.Namespace) -> int:
    from werewolf.transcript import render

    try:
        log = GameLog.from_json(Path(args.path).read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(
            errors="replace"
        )  # a model's odd characters must not crash a Windows console
    if args.prompt:
        from werewolf.promptview import rebuild
        from werewolf.promptview import render as render_prompts

        items = rebuild(log, keep_notes=args.notes)
        print(render_prompts(items, args.prompt, args.round, args.kind, args.spoke))
        return 0
    print(render(log, private=args.private, talk_only=args.talk))
    return 0


def _replay(args: argparse.Namespace) -> int:
    try:
        log = GameLog.from_json(Path(args.path).read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    if replay(log).to_json() == log.to_json():
        print("replay: exact match")
        return 0
    print("replay: DIFFERENT from the saved log")
    return 1


SMOKE_PROMPTS = {
    "wolf_chat": "You are Fay, a Werewolf. Your partner is Hal. It is night 1. Say one short "
    "line to Hal about who to kill, and add a short private note.",
    "night_target": "You are Fay, a Werewolf. Choose a victim from: Ada, Bo, Cy, Di, Eve. Use an "
    "empty string for no target. Add a short private note.",
    "bid": "You are Cy, a Villager. It is day 1. Bo said: 'I think Eve is suspicious.' Bid 0 to 3 "
    "tokens to speak (0 means stay quiet), write a message under 200 characters, choose an "
    "intent and a target name (or an empty string), add a short note, and give a belief about "
    "each other player: Ada, Bo, Di, Eve, Fay, Gus, Hal.",
    "vote": "You are Cy, a Villager. Vote for one of: Ada, Bo, Di, Eve, Fay, Gus, Hal. Give a "
    "reason under 100 characters, a short note, and a belief about each of them.",
    "memory": "Write a short summary of round 1: Ada was killed at night, Bo accused Eve, and "
    "nobody was removed by the vote.",
}


def _smoke(args: argparse.Namespace) -> int:
    from decimal import Decimal

    from werewolf import runtime
    from werewolf.agents.wire import WIRE_FOR, WireError, json_schema_for, to_action_json
    from werewolf.engine.actions import ACTION_FOR
    from werewolf.llm.types import Request
    from werewolf.runtime import build_client

    spend = Decimal(args.max_spend) if args.max_spend is not None else None
    try:
        client = build_client(args.model, spend)
    except RuntimeError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2

    async def run() -> int:
        bad = 0
        for kind in WIRE_FOR:
            request = Request(
                model=args.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You play Werewolf. Answer only with the JSON asked for.",
                    },
                    {"role": "user", "content": SMOKE_PROMPTS[kind]},
                ],
                schema=json_schema_for(kind),
                max_tokens=args.max_tokens or runtime.default_max_tokens(args.model),
            )
            try:
                done = await client.complete(request)
            except Exception as exc:
                print(f"{kind:13} FAILED  {type(exc).__name__}: {exc}")
                bad += 1
                continue
            try:
                converted = to_action_json(kind, done.text)
                if kind in ACTION_FOR:
                    ACTION_FOR[kind].model_validate_json(converted)
                verdict = "ok"
            except (WireError, ValueError) as exc:
                verdict = f"BAD ANSWER: {exc}"
                bad += 1
            flags = ("cache-hit " if done.cache_hit else "") + (
                "TRUNCATED " if done.truncated else ""
            )
            print(
                f"{kind:13} {verdict}  tokens in/out/cached {done.prompt_tokens}/"
                f"{done.completion_tokens}/{done.cached_tokens}  cost ${done.cost}  "
                f"{done.latency_s:.1f}s  {flags}"
            )
            if args.show:
                print(f"              {done.text}")
        print("smoke test:", "all schemas worked" if bad == 0 else f"{bad} problem(s)")
        return 0 if bad == 0 else 1

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="werewolf")
    commands = parser.add_subparsers(dest="command", required=True)

    play = commands.add_parser("play", help="play one game and save the log")
    play.add_argument("--seed", type=int, default=1)
    play.add_argument("--agents", choices=["scripted", "llm"], default="scripted")
    play.add_argument("--speaking-mode", choices=[m.value for m in SpeakingMode],
                      default=SpeakingMode.FLOOR_TOKENS.value)  # fmt: skip
    _add_game_options(play)
    play.add_argument("--data-dir", default="data/games")
    play.add_argument("--model", help="needed with --agents llm")
    play.add_argument("--max-spend", help="dollars; required for paid models")
    play.add_argument("--cache", choices=["fresh", "shared"], default="fresh")
    play.add_argument(
        "--notes", type=int, default=0, help="show each player its last N private notes"
    )
    play.add_argument(
        "--rpm", type=int, help="requests per minute to send (default: the provider's limit)"
    )
    play.add_argument(
        "--max-tokens", type=int, help="output limit per answer (default: 300, 700 for Claude)"
    )
    play.add_argument(
        "--persona",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="give each player a seeded table manner (blunt, chatty, cautious)",
    )
    play.set_defaults(run=_play)

    many = commands.add_parser("batch", help="play several model-driven games and report")
    many.add_argument("--games", type=int, default=1)
    many.add_argument("--first-seed", type=int, default=1)
    many.add_argument("--parallel", type=int, default=2)
    many.add_argument("--model", required=True)
    many.add_argument("--max-spend", help="dollars; required for paid models")
    many.add_argument(
        "--cache",
        choices=["fresh", "shared"],
        default="fresh",
        help="fresh: every game asks the model anew; shared: reuse cached answers (development)",
    )
    many.add_argument(
        "--speaking-mode",
        choices=[m.value for m in SpeakingMode],
        default=SpeakingMode.FLOOR_TOKENS.value,
    )
    _add_game_options(many)
    many.add_argument("--data-dir", default="data/games")
    many.add_argument(
        "--notes", type=int, default=0, help="show each player its last N private notes"
    )
    many.add_argument(
        "--rpm", type=int, help="requests per minute to send (default: the provider's limit)"
    )
    many.add_argument(
        "--max-tokens", type=int, help="output limit per answer (default: 300, 700 for Claude)"
    )
    many.add_argument(
        "--persona",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="give each player a seeded table manner (blunt, chatty, cautious)",
    )
    many.set_defaults(run=_batch)

    again = commands.add_parser("replay", help="replay a saved log and check it matches")
    again.add_argument("path")
    again.set_defaults(run=_replay)

    shown = commands.add_parser("show", help="print a saved game as readable text")
    shown.add_argument("path")
    shown.add_argument("--private", action="store_true", help="include roles, wolf chat and notes")
    shown.add_argument("--talk", action="store_true", help="only the messages and the votes")
    shown.add_argument("--prompt", metavar="PLAYER", help="rebuild the prompts this player saw")
    shown.add_argument("--round", type=int, help="with --prompt: only this round")
    shown.add_argument(
        "--kind",
        choices=["wolf_chat", "night_target", "bid", "vote", "memory"],
        help="with --prompt: only this kind of question",
    )
    shown.add_argument("--spoke", action="store_true", help="with --prompt: only posted messages")
    shown.add_argument(
        "--notes", type=int, default=0, help="with --prompt: the --notes value the game used"
    )
    shown.set_defaults(run=_show)

    check = commands.add_parser("smoke", help="call a real model once per answer shape")
    check.add_argument("--model", required=True)
    check.add_argument("--max-spend", help="dollars; required for paid models")
    check.add_argument("--show", action="store_true", help="print each raw model answer")
    check.add_argument(
        "--max-tokens", type=int, help="output limit per answer (default: 300, 700 for Claude)"
    )
    check.set_defaults(run=_smoke)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
