# Werewolf Coach

Eight AI agents play Werewolf in a group chat. Each one follows a strategy card, a short piece of text that tells it how to play its role. A tagger labels what every message does, a fact-check compares claims with the hidden roles, and an AI coach reads the games a side lost and writes a better card.

You can read finished games like a chat and tap any message to see what its player was privately thinking. A wolf's public lie sits next to its private note. You can also pick the cards for a game and watch the agents play it.

Live site: https://web-two-livid-72.vercel.app

## What it measures

- Which strategy cards win, per role, with a margin of error on every number.
- Whether agents follow their card, and which models ignore which cards.
- Whether a coach can write a card that beats the best hand-written one.
- Whether villagers catch a fake Seer.

A card effect is only called clear when the gap is about 30 points or more. Below that the site says "not clear yet", and it says so for any sample under 10 games.

## What the data shows so far

The experiments so far used small, cheap models, so the results are modest.

- In 54 games on `gpt-4.1-nano` (three wolf cards against three villager cards), wolves won 36, or 67%. Every gap between cards was 16 points with overlapping intervals, so no card effect is visible at that size.
- Agents followed some cards closely. Over those 54 games the fake-Seer card was followed 99% of the time and the lie-low card 24%. Wolves on the lie-low card talked only 18% less than wolves on the accuse-early card.
- The coach has run once end to end. It wrote a specific, checkable diagnosis (wolves turned on their own partner in 3 of the 4 lost games it read) and a new card. The card played one game per arm, which says nothing about whether it is better. The loop works. Whether it improves play is still open.

The rules changed on Oct 21, 2026, so results are always grouped by rule version.

## How the game works

Eight players: wolves, a Seer, a Doctor and villagers. At night the wolves choose a kill, the Doctor protects someone and the Seer checks someone. By day players bid for the floor, speak, and vote one player out. The engine owns every rule and every random draw. It never calls a model, and each agent only receives a view of what its player may know, so a hidden role cannot leak into a prompt. Every game is seeded and replays byte for byte.

## Run it

You need Python 3.12 and [uv](https://docs.astral.sh/uv/). Models are optional: scripted agents play for free.

```bash
uv sync
uv run python -m werewolf.cli play --seed 1 --agents scripted
uv run python -m werewolf.cli replay data/games/<id>.json
```

Model-driven games need a key in `.env` (copy `.env.example`) and a spend cap:

```bash
uv run python -m werewolf.cli play --seed 1 --agents llm --model gpt-4.1-nano --max-spend 0.10
```

The whole site, with its API and database, runs in Docker:

```bash
docker compose up -d --build
docker compose exec api python -m werewolf.cli app seed
```

The site is then at http://localhost:3100 and the API at http://localhost:8000. `docs/runbook.md` covers logs, spend caps and key rotation.

The coach:

```bash
uv run python -m werewolf.cli coach run --help
uv run python -m werewolf.cli coach show
```

## Money

Every paid model call goes through a cost ledger with a hard cap per provider, and a response cache makes re-runs free. In play mode on the site, a game has its own budget, and a daily and a total cap stop all visitors together. CI never makes a paid call.

## How it is built

| Part | What it is |
| --- | --- |
| `src/werewolf/engine` | Rules, state, phases, views and win checks. Pure and seeded. |
| `src/werewolf/agents` | Prompts, memory and the player agent, plus scripted agents for tests. |
| `src/werewolf/llm` | LiteLLM wrapper, cost ledger and response cache. |
| `src/werewolf/tagger` | Move tags, derived labels such as lie and fake claim, and fact-checking. |
| `src/werewolf/coach` | The LangGraph coach: diagnose, write a card, check it, test it against the champion. |
| `src/werewolf/api` | FastAPI service for games, replays, strategies, coach history and play mode. |
| `cards/` | The strategy cards, one YAML file each. Coach cards are in `cards/coach/`. |
| `web/` | The Next.js site. It talks only to the API. |

The API runs on Render, the site on Vercel and the database on Neon. On Render's free plan the API sleeps when idle. While it wakes, the site shows 15 hand-picked games saved in the site itself.

## Checks

```powershell
powershell -File scripts/check.ps1 fast
uv run pytest -q
cd web; npm test
```

`docs/DESIGN.md` is the system design, `SPEC.md` the build contract and `docs/decisions.md` the record of choices.

## License

MIT. See `LICENSE`.
