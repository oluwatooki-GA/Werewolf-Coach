"""Command line: play one scripted game and save its log, or replay a saved log.

uv run python -m werewolf.cli play --seed 1 --agents scripted
uv run python -m werewolf.cli replay data/games/<id>.json
"""

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from pydantic import ValidationError

from werewolf.agents.scripted import policy
from werewolf.engine.game import play_game
from werewolf.engine.log import GameLog, replay, to_log
from werewolf.engine.roles import Role
from werewolf.engine.setup import new_game
from werewolf.engine.state import Settings, SpeakingMode


def _play(args: argparse.Namespace) -> int:
    settings = Settings(speaking_mode=SpeakingMode(args.speaking_mode))
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="werewolf")
    commands = parser.add_subparsers(dest="command", required=True)

    play = commands.add_parser("play", help="play one game and save the log")
    play.add_argument("--seed", type=int, default=1)
    play.add_argument("--agents", choices=["scripted"], default="scripted")
    play.add_argument("--speaking-mode", choices=[m.value for m in SpeakingMode],
                      default=SpeakingMode.FLOOR_TOKENS.value)  # fmt: skip
    play.add_argument("--data-dir", default="data/games")
    play.set_defaults(run=_play)

    again = commands.add_parser("replay", help="replay a saved log and check it matches")
    again.add_argument("path")
    again.set_defaults(run=_replay)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
