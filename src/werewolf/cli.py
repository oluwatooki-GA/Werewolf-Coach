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
from decimal import Decimal
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


def _add_card_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cards",
        default="",
        help="strategy card for each role, such as wolf=wolf.lie_low,seer=seer.reveal "
        "(roles: wolf, villager, seer, doctor)",
    )
    parser.add_argument(
        "--card-seat",
        action="append",
        default=[],
        metavar="NAME=CARD",
        help="strategy card for one seat, such as Fay=wolf.lie_low; beats --cards",
    )


def _add_claim_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--claim-check-model",
        help="model that fact-checks each game's messages (default: the player model)",
    )
    parser.add_argument(
        "--no-claim-check", action="store_true", help="skip the fact-check of what players said"
    )


def _split_pairs(items: list[str], what: str) -> dict[str, str]:
    pairs = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ValueError(f"{what} '{item}' should look like NAME=CARD")
        pairs[key.strip()] = value.strip()
    return pairs


def _cards_from(args: argparse.Namespace) -> tuple[dict[Role, str], dict[str, str]]:
    """(card by role, card by seat) from the command line. Raises ValueError if it is unreadable."""
    from werewolf.strategies.cards import ROLE_FOR_PREFIX

    by_role = {}
    for prefix, card_id in _split_pairs(
        [x for x in args.cards.split(",") if x.strip()], "--cards entry"
    ).items():
        if prefix not in ROLE_FOR_PREFIX:
            raise ValueError(f"unknown role '{prefix}'; use one of: {', '.join(ROLE_FOR_PREFIX)}")
        by_role[ROLE_FOR_PREFIX[prefix]] = card_id
    return by_role, _split_pairs(args.card_seat, "--card-seat")


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
    claim_model = None if args.no_claim_check else (args.claim_check_model or args.model)
    try:
        by_role, by_seat = _cards_from(args)
        client = runtime.build_client(args.model, spend, requests_per_minute=args.rpm)
    except (RuntimeError, ValueError) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(
            runner.run_batch(
                client,
                args.model,
                seeds,
                settings=_settings(args, summarize_rounds=True),
                parallel=getattr(args, "parallel", 1),
                cache=args.cache,
                data_dir=Path(args.data_dir),
                announce=lambda played: print(runner.format_game(played), flush=True),
                keep_notes=args.notes,
                use_personas=args.persona,
                max_tokens=args.max_tokens
                or runtime.default_max_tokens(args.model, args.message_chars),
                cards_by_role=by_role,
                cards_by_seat=by_seat,
                claim_model=claim_model,
                claim_tokens=runtime.default_max_tokens(claim_model or args.model),
            )
        )
    except ValueError as exc:  # a card that does not fit its seat, found before any model call
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    print(runner.format_report(report))
    return 1 if report.stopped is not None or any(p.leaks for p in report.played) else 0


def _batch(args: argparse.Namespace) -> int:
    return _llm(args, list(range(args.first_seed, args.first_seed + args.games)))


def _play(args: argparse.Namespace) -> int:
    if args.agents == "llm":
        return _llm(args, [args.seed])
    if args.cards or args.card_seat:
        print("--cards and --card-seat need --agents llm", file=sys.stderr)
        return 2
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
    if args.tags:
        from werewolf.tagger.show import render_tags
        from werewolf.tagger.tags import load_tags

        tagfile = load_tags(Path(args.path))
        if tagfile is None:
            print(f"\nno tags yet: run  tag {args.path} --model <model>", file=sys.stderr)
            return 1
        print("\n" + render_tags(log, tagfile, private=args.private))
    return 0


def _game_files(paths: list[str]) -> list[Path]:
    from werewolf.tagger.tags import game_files

    return game_files(paths)


def _label(args: argparse.Namespace) -> int:
    """Label a seeded sample of messages by hand; stop with q and come back later."""
    from werewolf.tagger.labels import collect, load_labels, run_session, sample

    store = Path(args.file)
    items = sample(collect(args.paths), args.count, args.seed)
    if not items:
        print("no messages found in those games", file=sys.stderr)
        return 2
    run_session(items, store, ask=input, out=print)
    print(f"{len(load_labels(store))} labels in {store}")
    return 0


def _accuracy(args: argparse.Namespace) -> int:
    """Score the tagger against your labels. Exit 1 if there is nothing to compare."""
    from werewolf.tagger.labels import accuracy, format_accuracy, load_labels

    labels = load_labels(Path(args.file))
    if not labels:
        print(f"no labels in {args.file}: run the label command first", file=sys.stderr)
        return 1
    report = accuracy(args.paths, labels)
    if not report.messages:
        print("none of your labeled messages has a tag: run the tag command on those games")
        return 1
    print(format_accuracy(report))
    return 0


def _tag(args: argparse.Namespace) -> int:
    """Tag the public messages of saved games. Exit 1 if the run had to stop early."""
    from decimal import Decimal

    from werewolf import runtime
    from werewolf.tagger.tagger import TagStopped, tag_game
    from werewolf.tagger.tags import TagFile, save_tags, tags_path

    spend = Decimal(args.max_spend) if args.max_spend is not None else None
    try:
        client = runtime.build_client(args.model, spend, requests_per_minute=args.rpm)
    except RuntimeError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    limit = args.max_tokens or runtime.default_max_tokens(args.model)

    async def run() -> int:
        code, total, tagged_games = 0, Decimal("0"), 0
        for path in _game_files(args.paths):
            if tags_path(path).exists() and not args.again:
                print(f"{path}: already tagged (use --again to redo)")
                continue
            try:
                log = GameLog.from_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError) as exc:
                print(f"{path}: cannot read: {exc}", file=sys.stderr)
                code = 2
                continue
            try:
                result = await tag_game(log, client, args.model, max_tokens=limit)
            except TagStopped as stop:
                total += stop.run.cost
                print(f"{path}: STOPPED: {stop}; nothing saved, a rerun resumes from the cache")
                print(f"spent ${total:.6f}")
                return 1
            if (
                not result.tags and result.untagged
            ):  # nothing worked: a file now would block a retry
                print(f"{path}: nothing could be tagged, nothing saved", file=sys.stderr)
                for line, why in sorted(result.untagged.items())[:3]:
                    print(f"    {line}: {why}", file=sys.stderr)
                code = 1
                continue
            save_tags(path, TagFile(model=args.model, tags=result.tags, untagged=result.untagged))
            total += result.cost
            tagged_games += 1
            print(
                f"{path}: {len(result.tags)} tagged, {len(result.untagged)} untagged, "
                f"{result.cache_hits} from cache, ${result.cost:.6f}"
            )
            for line, why in sorted(result.untagged.items()):
                print(f"    {line}: {why}")
        print(f"{tagged_games} game(s) tagged, ${total:.6f}")
        return code

    return asyncio.run(run())


def _ground(args: argparse.Namespace) -> int:
    """Fact-check what players said against the public log. Exit 1 if the run had to stop."""
    from decimal import Decimal

    from werewolf import runtime
    from werewolf.engine.record import numbered_speeches
    from werewolf.tagger.grounding import GroundStopped, check_game

    spend = Decimal(args.max_spend) if args.max_spend is not None else None
    try:
        client = runtime.build_client(args.model, spend, requests_per_minute=args.rpm)
    except RuntimeError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    limit = args.max_tokens or runtime.default_max_tokens(args.model)

    async def run() -> int:
        code, checked, flagged, total = 0, 0, 0, Decimal("0")
        for path in _game_files(args.paths):
            try:
                log = GameLog.from_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError) as exc:
                print(f"{path}: cannot read: {exc}", file=sys.stderr)
                code = 2
                continue
            try:
                result = await check_game(log, client, args.model, max_tokens=limit)
            except GroundStopped as stop:
                print(f"{path}: STOPPED: {stop}; spent ${total + stop.run.cost:.6f}")
                return 1
            checked += result.checked
            flagged += len(result.flagged)
            total += result.cost
            print(
                f"{path}: {result.checked} messages checked, {len(result.flagged)} with an "
                f"unsupported claim, {len(result.failed)} could not be checked, "
                f"${result.cost:.6f}"
            )
            speakers = {line: s.speaker for line, s in numbered_speeches(log.events)}
            for line, claim in sorted(result.flagged.items()):
                print(f"    {line} {speakers[line]}: {claim}")
            for line, why in sorted(result.failed.items()):
                print(f"    {line}: could not check: {why}")
        rate = 100 * flagged / checked if checked else 0.0
        print(f"unsupported claims: {flagged} of {checked} messages ({rate:.0f}%), ${total:.6f}")
        return code

    return asyncio.run(run())


def _adherence(args: argparse.Namespace) -> int:
    from werewolf.tagger.adherence import adherence, format_adherence
    from werewolf.tagger.tags import load_tags

    pairs, skipped = [], 0
    for path in _game_files(args.paths):
        try:
            log = GameLog.from_json(path.read_text(encoding="utf-8"))
            tagfile = load_tags(path)
        except (OSError, ValueError, ValidationError) as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            return 2
        if tagfile is None:
            skipped += 1
        else:
            pairs.append((log, tagfile))
    print(format_adherence(adherence(pairs)))
    if skipped:
        print(f"{skipped} game(s) left out: no tags yet (run the tag command first)")
    return 0


def _spend(text: str | None) -> Decimal | None:
    return Decimal(text) if text is not None else None


def _coach_run(args: argparse.Namespace) -> int:
    """Run coach generations. Exit 1 if a cap or an error stopped it, 2 if it could not start."""
    from werewolf import runtime
    from werewolf.coach.history import family_tree
    from werewolf.coach.run import START_CHAMPION, CoachPlan, check_plan, run_coach
    from werewolf.coach.steps import CoachError, CoachStopped

    plan = CoachPlan(
        side=args.side,
        generations=args.generations,
        games=args.games,
        first_seed=args.first_seed,
        champion=args.champion or START_CHAMPION[args.side],
        evidence=args.evidence,
        player_model=args.player_model,
        coach_model=args.coach_model,
        check_model=args.check_model,
        parallel=args.parallel,
        run=args.tag,
    )
    try:
        check_plan(plan)
        coach = runtime.build_client(
            args.coach_model, _spend(args.max_spend_coach), flag="--max-spend-coach"
        )
        players = runtime.build_client(
            args.player_model,
            _spend(args.max_spend_players),
            requests_per_minute=args.rpm,
            flag="--max-spend-players",
        )
    except (RuntimeError, ValueError) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    code = 0
    try:
        asyncio.run(
            run_coach(
                coach,
                players,
                plan,
                settings=Settings(summarize_rounds=True),
                say=lambda text: print(text, flush=True),
            )
        )
    except CoachStopped as exc:
        print(f"STOPPED: {exc}; the generation in progress was not saved, run again to resume")
        code = 1
    except CoachError as exc:
        print(f"the coach could not finish: {exc}", file=sys.stderr)
        code = 1
    print(family_tree(args.side))
    return code


def _coach_show(args: argparse.Namespace) -> int:
    from werewolf.coach.history import family_tree

    print(family_tree(args.side))
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
    _add_card_options(play)
    _add_claim_options(play)
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
        "--max-tokens", type=int, help="output limit per answer (default: 300, 1000 for Claude)"
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
    _add_card_options(many)
    _add_claim_options(many)
    many.add_argument("--data-dir", default="data/games")
    many.add_argument(
        "--notes", type=int, default=0, help="show each player its last N private notes"
    )
    many.add_argument(
        "--rpm", type=int, help="requests per minute to send (default: the provider's limit)"
    )
    many.add_argument(
        "--max-tokens", type=int, help="output limit per answer (default: 300, 1000 for Claude)"
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
        "--tags", action="store_true", help="add the tagger's moves (labels need --private)"
    )
    shown.add_argument(
        "--notes", type=int, default=0, help="with --prompt: the --notes value the game used"
    )
    shown.set_defaults(run=_show)

    tag = commands.add_parser("tag", help="label the moves in saved games")
    tag.add_argument("paths", nargs="+", help="game logs or folders of them")
    tag.add_argument("--model", required=True)
    tag.add_argument("--max-spend", help="dollars; required for paid models")
    tag.add_argument("--again", action="store_true", help="tag games that already have tags")
    tag.add_argument("--rpm", type=int, help="requests per minute to send")
    tag.add_argument("--max-tokens", type=int, help="output limit per answer")
    tag.set_defaults(run=_tag)

    label = commands.add_parser("label", help="label messages by hand to check the tagger")
    label.add_argument("paths", nargs="+", help="game logs or folders of them")
    label.add_argument("--count", type=int, default=100, help="how many messages (default: 100)")
    label.add_argument("--seed", type=int, default=1, help="which sample (default: 1)")
    label.add_argument("--file", default="data/labels/mine.jsonl")
    label.set_defaults(run=_label)

    score = commands.add_parser("accuracy", help="score the tagger against your labels")
    score.add_argument("paths", nargs="+", help="tagged game logs or folders of them")
    score.add_argument("--file", default="data/labels/mine.jsonl")
    score.set_defaults(run=_accuracy)

    ground = commands.add_parser("ground", help="fact-check messages against the public log")
    ground.add_argument("paths", nargs="+", help="game logs or folders of them")
    ground.add_argument("--model", required=True)
    ground.add_argument("--max-spend", help="dollars; required for paid models")
    ground.add_argument("--rpm", type=int, help="requests per minute to send")
    ground.add_argument("--max-tokens", type=int, help="output limit per answer")
    ground.set_defaults(run=_ground)

    follow = commands.add_parser("adherence", help="do players follow their strategy card?")
    follow.add_argument("paths", nargs="+", help="tagged game logs or folders of them")
    follow.set_defaults(run=_adherence)

    check = commands.add_parser("smoke", help="call a real model once per answer shape")
    check.add_argument("--model", required=True)
    check.add_argument("--max-spend", help="dollars; required for paid models")
    check.add_argument("--show", action="store_true", help="print each raw model answer")
    check.add_argument(
        "--max-tokens", type=int, help="output limit per answer (default: 300, 1000 for Claude)"
    )
    check.set_defaults(run=_smoke)

    coach = commands.add_parser("coach", help="the coach: write better cards from lost games")
    coach_commands = coach.add_subparsers(dest="coach_command", required=True)
    side_choices = ["wolf", "villager"]

    coach_run = coach_commands.add_parser("run", help="run coach generations for one side")
    coach_run.add_argument("--side", choices=side_choices, required=True)
    coach_run.add_argument("--generations", type=int, default=1, help="how many in all")
    coach_run.add_argument("--games", type=int, default=6, help="games per arm (default: 6)")
    coach_run.add_argument("--first-seed", type=int, default=1000)
    coach_run.add_argument("--champion", help="card to start from (default: the plan's choice)")
    coach_run.add_argument(
        "--evidence", nargs="+", required=True, help="folders of games the coach reads"
    )
    coach_run.add_argument("--player-model", default="gpt-4.1-nano")
    coach_run.add_argument("--coach-model", default="claude-sonnet-5-5")
    coach_run.add_argument("--check-model", default="claude-haiku-5-5")
    coach_run.add_argument("--max-spend-players", help="dollars; required for paid models")
    coach_run.add_argument("--max-spend-coach", help="dollars; required for paid models")
    coach_run.add_argument("--parallel", type=int, default=3)
    coach_run.add_argument("--rpm", type=int, help="player requests per minute")
    coach_run.add_argument("--tag", default="", help="goes into new card ids (a fresh history)")
    coach_run.set_defaults(run=_coach_run)

    coach_show = coach_commands.add_parser("show", help="print a side's family tree of champions")
    coach_show.add_argument("--side", choices=side_choices, required=True)
    coach_show.set_defaults(run=_coach_show)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
