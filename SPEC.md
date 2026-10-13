# Spec: Werewolf Coach

Source of truth for behavior: `docs/DESIGN.md` (decided, not redesigned here). Stack answers: `docs/decisions.md`. This file adds the build contract: commands, structure, style, tests, boundaries, and a spec per milestone.

## Objective

A lab where AI agents play 8-player Werewolf with swappable strategy cards, to find which strategies work per role, whether agents follow their card, whether an AI coach can write better cards, and whether villagers can catch a fake Seer. Users: the builder (Tooki) running experiments, and visitors who replay games and play one seat on the site.

Done means: the README headline numbers in DESIGN 11.2 are filled with real results, an open dataset is published, and a tagged release deploys with no manual steps.

## Tech Stack

| Area | Choice |
| --- | --- |
| Language / packages | Python 3.12 (pinned in `.python-version`), uv only |
| LLM layer | LiteLLM (all calls through the cost ledger) |
| Game loop | Plain `asyncio`, engine controls turns |
| Actions | Pydantic v2 models, validated by the engine |
| Coach (M5) | LangGraph |
| DB | Postgres (Docker locally, Neon at M7), Parquet exports in `data/` |
| API (M7) | FastAPI + WebSockets |
| Web (M7) | Next.js + TypeScript in `web/`, npm |
| Observability (M7) | Langfuse via LiteLLM callback, JSON logs |
| Hosting (M7) | Vercel, Fly.io, Neon. No AWS. |
| Quality | ruff, mypy, pytest |
| CI | GitHub Actions |

Dependencies are added only when their milestone needs them (LangGraph at M5, FastAPI at M7).

## Commands

All run from the repo root in PowerShell. Never `pip`.

```
Setup:        uv sync
Add dep:      uv add <pkg>            (ask first)
Test:         uv run pytest -q
Test+cov:     uv run pytest --cov=src/werewolf --cov-report=term-missing
Lint:         uv run ruff check .
Format:       uv run ruff format .
Types:        uv run mypy src
All checks:   uv run ruff check . ; uv run mypy src ; uv run pytest -q
Play 1 game:  uv run python -m werewolf.cli play --seed 1 --agents scripted
Replay:       uv run python -m werewolf.cli replay data/games/<id>.json
Local DB:     docker compose up -d db
API (M7):     uv run uvicorn werewolf.api.main:app --reload
Web (M7):     cd web ; npm run dev
```

PyCharm: interpreter is the uv-created `.venv`; run configs call the same commands.

## Project Structure

```
src/werewolf/
  engine/       rules, state, phases, views, win checks (no LLM imports, ever)
  agents/       prompts, memory, player agent, scripted fake agents
  llm/          LiteLLM wrapper, cost ledger, response cache
  strategies/   card loader and checks
  tagger/       move tagger, derived labels
  experiments/  E1 to E9 runners, stats, exports
  coach/        LangGraph coach (M5)
  store/        Postgres access, Parquet export
  api/          FastAPI (M7)
  cli.py
cards/          strategy cards (YAML), one file per card
tests/          unit, scripted games, leak, replay, integration
evals/results/  committed eval JSON
recordings/     recorded model responses for offline CI
data/           git-ignored Parquet and game logs
web/            Next.js app (M7)
docs/           DESIGN.md, decisions.md, progress.md, runbook.md (M7)
```

## Code Style

Typed, small functions, frozen dataclasses or Pydantic for data, no classes where a function works. The engine is pure and seeded: no clock, no global random, no network.

```python
from random import Random

def resolve_bids(bids: dict[str, int], spoken: dict[str, int], rng: Random) -> str | None:
    """Highest bid speaks; ties go to whoever spoke least today, then random."""
    live = {p: b for p, b in bids.items() if b > 0}
    if not live:
        return None
    top = max(live.values())
    tied = sorted(p for p, b in live.items() if b == top)
    least = min(spoken.get(p, 0) for p in tied)
    return rng.choice([p for p in tied if spoken.get(p, 0) == least])
```

Rules: `snake_case` functions, `PascalCase` models, type hints everywhere, ruff defaults plus import sorting, line length 100. Plain-language text in UI and README, no em dashes anywhere.

## Testing Strategy

pytest. Offline and free by default; paid calls never run in CI.

| Level | What | Where |
| --- | --- | --- |
| Unit | Every rule: kills, saves, Seer checks, bid ties, vote ties, win checks, round limit | `tests/engine/` |
| Scripted games | Fake agents with a known outcome | `tests/scripted/` |
| Leak test | Plant a code word as a wolf secret, fail if it appears in any non-wolf prompt | `tests/test_leak.py` |
| Replay | Same seed and log reproduce the game exactly | `tests/test_replay.py` |
| Card format | Length, fields, expected moves from the move set | `tests/test_cards.py` |
| Integration | One full game from recorded responses | `tests/test_integration.py` |
| Evals | Rule following, adherence, coach validity, cost, speed | `evals/results/*.json` |

Coverage: engine and ledger at 90%+ lines; elsewhere no hard number, but every rule has a test. Bugs get a failing test first.

## Boundaries

**Always**
- Keep the engine free of LLM code. Agents get a `PlayerView`, never the game state.
- Send every paid call through the cost ledger (hard stop $4.50 per provider).
- Keep strategies in `cards/`, never in code. Log every game fully with its seed.
- Run ruff, mypy and pytest before a commit. Write numbers to `docs/progress.md` at each gate.
- Use plain language, no em dashes.

**Ask first**
- Adding any dependency or paid service (including Fly.io, Neon or Vercel plan changes).
- Changing the DB schema after M2, the card format, the move set, or the CI files.
- Any run that spends real money beyond the milestone's planned budget.
- Raising a spend cap or experiment size.

**Never**
- Commit `.env` or any key. Keys live in `.env` (git-ignored) and, later, host secrets.
- Use AWS, pip, or poetry. Use fine-tuning.
- Let CI make paid calls.
- Remove or skip a failing test without approval.
- Show one agent another agent's secret, or send a private note to anyone.

## Capability Map

| Module id | Milestone | Responsibility | Depends on |
| --- | --- | --- | --- |
| `speed-test` | M0 | Done. `gpt-4.1-nano` picked. | none |
| `engine` | M1 | Rules, bidding, views, logging, replay, fake agents, CI, cost ledger | none |
| `agents` | M2 | Prompts, actions, beliefs, memory, caching layout, response cache, leak test | engine |
| `strategy-tagger` | M3 | 12 cards, card checks, move tagger, derived labels | engine, agents |
| `experiments` | M4 | E1 to E3, E5, E6, exports | agents, strategy-tagger |
| `coach` | M5 | LangGraph coach, champion vs challenger (E4) | experiments |
| `extra-runs` | M6 | E7, E9, caching experiment | experiments |
| `app-deploy` | M7 | API, web app, play mode, deploy, Langfuse, health, fault switches | engine, agents, strategy-tagger |
| `ship` | M8 | README, findings, dataset, demo | all |

Build order: `engine`, `agents`, `strategy-tagger`, `experiments`, then `coach` and `extra-runs`, then `app-deploy`, then `ship`. Each module is planned and built on its own (`/plan Milestone Mn`). Module details follow; the design sections cited are the full requirements.

## Module Specs

### engine (M1) - DESIGN 2, 5.1, 5.4, 5.7, 7
- **Scope:** repo and uv setup, CI (`ci.yml`), cost ledger, full rules including floor-token bidding plus the fixed-order and free-bid baselines, `PlayerView` builder, JSON game log, replay, scripted fake agents, safe-default handling.
- **Interface:** `play_game(seed, settings, agents) -> GameState`; `to_log(state) -> GameLog`; `replay(log) -> GameLog`; `make_view(state, player) -> PlayerView`. Agents implement `async act(view, task) -> Action`.
- **Success criteria:**
  - Rule tests pass for kills, saves, Seer checks, bid ties, free reply after an accusation, vote ties, win checks and the 6-round limit.
  - A scripted game ends with its predetermined winner.
  - Replaying a log gives a byte-identical log.
  - Illegal or broken output gets one retry, then the safe default, counted as a failure.
  - The ledger blocks a call that would pass $4.50 for a provider (tested with fake prices).
  - `engine/` imports no LLM or network library (checked by a test).
- **Gate:** all of the above pass in CI; results in `docs/progress.md`.

### agents (M2) - DESIGN 5.2, 5.3, 5.6, 8
- **Scope:** player prompt (rules, role, card, beliefs, memory, public log, task in cache-friendly order), Pydantic actions with beliefs and private note, round-end memory rewrite, response cache by prompt hash, `prompt_cache_key` use, LiteLLM wrapper with per-call tokens and cost, leak test.
- **Success criteria:** leak test fails the build when a wolf code word reaches a non-wolf prompt; one call per player per speaking turn; cached re-runs cost $0; per-call and per-game cost and cached-token share are logged.
- **Gate:** 10 real `gpt-4.1-nano` games with under 2% rejected actions and no leaks; real cost per game written into DESIGN 8.1 and `docs/progress.md`; experiment sizes re-planned from it.

### strategy-tagger (M3) - DESIGN 3, 5.5
- **Scope:** 12 starter cards in `cards/` (3 per role, summarised in our own words, source credited), card loader and checks (80 words or fewer, only knowable facts, expected moves from the move set), Haiku batch tagger, Sonnet reference tagger, tagger cache by text hash, derived labels (`lie`, `fake_claim`, `counter_claim`, `bus`, `shield`, `hit`) computed in code.
- **Success criteria:** cards load and swap by ID with no code change; a bad card fails the check with a clear message; derived labels are correct on scripted games; agreement with your 100 labels and between the two taggers reported per move.
- **Gate:** tagger agreement in `docs/progress.md`. Your part: approve the cards, label 100 messages, check the ~40 disagreements.

### experiments (M4) - DESIGN 6, 6.1
- **Scope:** runners for E1, E2, E3, E5, E6 on shared seeds, 4 games in parallel, resume after a crash, Parquet export, win rates with intervals and "not clear yet" flags.
- **Success criteria:** every pairing has its planned number of clean games (re-planned at M2); no result without an interval; rule-break and fallback rates reported per card.
- **Gate:** counts and exports in `docs/progress.md`; spend under the cap.

### coach (M5) - DESIGN 3.4
- **Scope:** LangGraph graph: read, diagnose, write challenger, check, test; Sonnet 5.5; generation history saved.
- **Success criteria:** a challenger that fails format or rule checks never plays; challengers play the champion on the same seeds; the champion changes only on a clear win; each generation's card, diagnosis and result are stored.
- **Gate:** 3 generations per side completed and logged. Your part: read the diagnoses.

### extra-runs (M6) - DESIGN 6 (E7, E9), 8.2
- **Scope:** E7 on Haiku 5.5, E9 on Groq or Cerebras free tier (spread across days), caching on/off on the same 5 games.
- **Success criteria:** results committed to `evals/results/`; free-tier rate limits handled without losing games.
- **Gate:** spend still under the ledger caps.

### app-deploy (M7) - DESIGN 5.8, 5.9, 9
- **Scope:** FastAPI endpoints, replay viewer, strategy board, play mode with a turn timer (Haiku 5.5, $0.10 a day and $1 total caps), MCP server, Dockerfile, `fly.toml`, `release.yml`, `eval-check.yml`, Langfuse, JSON logs, `/health`, `/metrics`, fault switches (test-only), `docs/runbook.md`.
- **Success criteria:** a human finishes a game; caps pause play mode while replays keep working; fault switches are off outside tests; no keys in the image.
- **Gate:** a tagged release deploys with no manual steps.

### ship (M8) - DESIGN 11.2, 11.3
- **Scope:** README as a product spec, findings in your own words, Hugging Face dataset, demo video.
- **Success criteria:** every README headline number comes from committed results; the dataset has no keys or private user data.

## Success Criteria (project)

- All gates M1 to M7 pass with numbers in `docs/progress.md`.
- Total spend stays under $4.50 per provider and under about $8 overall.
- A game replays exactly from its seed and log.
- Zero secret leaks in CI.

## Open Questions

1. **Python version:** I pinned 3.12 because the machine has 3.14 and I haven't checked LiteLLM and LangGraph on it. OK, or do you want 3.13 or 3.14?
2. **`web/` package manager:** npm by default (uv covers Python only). OK?
3. **Per-module spec files:** I kept module specs in this one file to save files. Say so if you want `SPEC-<id>.md` per module instead.
4. **Repo hygiene:** there is no `.gitignore` yet. M1's first task adds one covering `.env`, `.venv`, `data/` and `node_modules`. `docs/` is untracked, so decide whether to commit it with the first commit.
