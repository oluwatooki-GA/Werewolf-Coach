# Tasks: M1, setup and engine with no AI

Plan: `tasks/plan.md`. Commands: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`, `powershell -File scripts/check.ps1 task`.
Every task ends with `check.ps1 task` passing. Tests come first (red, then green).

## Phase 1: Foundation

- [x] **T1: Project bootstrap, `.env` protection and architecture test** (S)
  - Create `pyproject.toml` (Python 3.12, `pydantic`; dev `ruff`, `mypy`, `pytest`), `.python-version`, `uv.lock`, empty packages `engine/`, `agents/`, `llm/`, ruff (line length 100, import sorting) and mypy strict config, and `tests/test_architecture.py`.
  - `.env` before the first commit: `.gitignore` already exists with `.env` ignored (written during `/constraints`); T1 verifies it and adds `.env.example` (variable names only, no values). There is no secrets scanner (removed by the owner), so the floor guard's `.env` check is the protection.
  - Acceptance:
    - `.env` is ignored (`git check-ignore .env` succeeds) and not tracked (`git ls-files .env` is empty); `.env.example` is committed, `.env` is not.
    - `floor_guard.py` reports no `env-tracked` or `env-not-ignored` finding before the first commit.
    - `uv sync` works from a clean checkout.
    - `check.ps1 task` runs ruff, mypy and pytest for real (no "NOT RUN").
    - Architecture test, using stdlib `ast` and handling relative imports and `__import__`/`importlib`: (a) `engine/` imports only stdlib, `pydantic` and `werewolf.engine`; (b) `agents/` imports from `werewolf.engine` only `views` and `actions`; (c) `litellm`, `openai`, `anthropic` are imported only under `llm/`.
    - The test also proves itself: it writes a violating file to a temp dir and checks each rule fails.
  - Verify: `uv run pytest tests/test_architecture.py -q`; `uv run python --version` shows 3.12; `git check-ignore .env`.
  - Note: `floor_guard.py` flags `bar-edited` for the scripts and `.constraints/` until they are committed. That first commit is your approval of them, so those findings are expected for it.
  - Files: `pyproject.toml`, `.python-version`, `.env.example`, `src/werewolf/{__init__,engine/__init__,agents/__init__,llm/__init__}.py`, `tests/test_architecture.py` (plus generated `uv.lock`; `.gitignore` already exists)
  - Depends on: none

- [x] **T2: Cost ledger** (S)
  - `llm/ledger.py`: `Ledger(path, caps)`, `reserve(key, estimate)`, `settle(reservation, actual)`, `release(reservation)`, `remaining(key)`.
  - Acceptance:
    - Default caps: `openai` $4.50, `anthropic` $4.50, `groq` and `cerebras` $0.
    - A reservation that would pass the cap raises `LedgerBlocked`; exactly the cap is allowed, one cent over is not.
    - Unknown key fails closed.
    - Reserved-but-unsettled money counts against the cap; `release` returns it after a failed call.
    - State persists to a JSON file (atomic write) and a second `Ledger` on the same file sees the spend.
    - Uses `Decimal`, no floats.
  - Verify: `uv run pytest tests/test_ledger.py -q` using fake prices and a temp file.
  - Files: `src/werewolf/llm/ledger.py`, `tests/test_ledger.py`
  - Depends on: T1

### Checkpoint 1: Foundation
- [x] `check.ps1 task` passes with real tools
- [x] Architecture test catches planted violations
- [x] Ledger blocks at $4.50 in tests
- [ ] Review with human before proceeding

## Phase 2: A game that can start and see

- [ ] **T3: Seeded setup, state and first player views** (M)
  - `engine/state.py` (roles, players, settings, game state), `engine/events.py` (public and private event types), `engine/setup.py` (`new_game(seed, settings)`), `engine/views.py` (`PlayerView`, `make_view`).
  - Acceptance:
    - 8 players: 2 wolves, 1 Seer, 1 Doctor, 4 villagers, assigned from the seed.
    - Same seed gives identical roles and seats; different seeds differ.
    - Settings include speaking mode, 8 turns, 6 rounds, 3 tokens, 300-char cap, optional card id per seat (logged only).
    - A wolf's view shows its partner; no other view does.
    - `PlayerView` is a frozen model with no reference to game state.
    - **Basic leak test (`tests/engine/test_leak_views.py`, added at approval):** for every seat in a hand-built state that contains a planted wolf chat line and a planted Seer result (each with a unique code word), no `PlayerView` serialised to JSON contains: (a) another player's role, except the wolf partner for a wolf, (b) the wolf chat unless the viewer is a wolf, (c) the Seer's result unless the viewer is the Seer. The test runs over all 8 seats and over several seeds, and fails loudly if the planted words show up anywhere they should not. Private event types (wolf chat, Seer result) are defined here in `events.py` so the test can exist before T5.
  - Verify: `uv run pytest tests/engine/test_setup.py tests/engine/test_views.py tests/engine/test_leak_views.py -q`
  - Files: `engine/{state,events,setup,views}.py`, `tests/engine/test_setup.py`, `tests/engine/test_views.py`, `tests/engine/test_leak_views.py`
  - Depends on: T1

- [ ] **T4: Action layer and scripted agents** (M)
  - `engine/actions.py`: tasks (wolf chat, night target, bid, vote), action models (optional `note`, `beliefs`), `Agent` protocol, `ask(agent, view, task, check)`. `agents/scripted.py`: scripted agents driven by a function or queue.
  - Acceptance:
    - A valid action passes through unchanged.
    - An invalid action (bad schema or illegal for the state) gets one retry whose task carries the error text.
    - Two failures give the safe default (bid 0, abstain, no target) and are counted as a rule-following failure.
    - An agent that raises is handled the same way; the engine never crashes.
    - Every raw response is recorded in order.
  - Verify: `uv run pytest tests/engine/test_actions.py -q`
  - Files: `engine/actions.py`, `agents/scripted.py`, `tests/engine/test_actions.py`
  - Depends on: T3

## Phase 3: Rules, one phase at a time

- [ ] **T5: Night phase** (M)
  - `engine/night.py`: wolf chat, targets, Seer check, Doctor protect, resolution, morning announcement.
  - Acceptance:
    - Unprotected target dies; protected target survives and the announcement says nobody died.
    - Doctor may protect herself.
    - Seer learns the target's true role, visible only in her later views.
    - Wolf chat is visible only to wolves, and the Seer's result only to the Seer. T3's leak test is extended to run over a real played night, so the planted code words come from actual play and never appear in a view they should not.
    - Disagreeing wolf targets are settled by the seeded rng, same result on replay of the seed.
    - Dead Seer or Doctor skip their action. A dead player's role stays hidden.
  - Verify: `uv run pytest tests/engine/test_night.py tests/engine/test_leak_views.py -q`
  - Files: `engine/night.py`, `tests/engine/test_night.py`, `tests/engine/test_leak_views.py`
  - Depends on: T4

- [ ] **T6: Day discussion with floor tokens** (M, highest risk)
  - `engine/day.py`: sealed bids 0 to 3, highest speaks and pays, tie-breaks (least spoken today, then rng), listening notices, free reply, 8 turns or early stop, tokens reset each day.
  - Acceptance: each edge case below is its own named test in `tests/engine/test_day_tokens.py`, written before the code. All must pass.
    - `test_bid_ties_go_to_least_spoken`: with equal top bids, the player who has spoken least today speaks; a second tie among those is settled by the rng.
    - `test_zero_bid_means_listening`: a bid of 0 never speaks and produces a public "listening" event.
    - `test_all_listening_ends_the_day`: when every living player bids 0, the day ends early, before 8 turns.
    - `test_right_of_reply_once_per_day`: a message that accuses by name (intent `accuse` plus target) gives that player one free reply next (no bid, no cost, counts as one of the 8 turns, only if alive); a second accusation of the same player the same day gives no second reply.
    - `test_tokens_lost_at_nightfall`: unused tokens are gone after the day, and every living player starts the next day with 3.
    - `test_no_overbidding`: a bid above tokens left is illegal; it gets one retry, then falls back to bid 0.
    - `test_all_randomness_through_seeded_rng`: the test makes every global `random` function raise, then plays a day with ties; it passes only if all choices come from the game's `Random(seed)`. The same seed gives the same day, a different seed can differ.
    - Also covered, as further named tests: `test_highest_bid_speaks_and_pays_exactly_its_bid` and `test_result_ignores_answer_order` (agents answering in reverse order give the same day).
  - Verify: `uv run pytest tests/engine/test_day_tokens.py -q` (all seven named tests listed in the output)
  - Files: `engine/day.py`, `tests/engine/test_day_tokens.py`
  - Depends on: T5

- [ ] **T7: Day baselines** (S)
  - Fixed order and free bidding (0 to 4, no cost) as settings of the same day runner.
  - Acceptance:
    - Fixed order: living players speak in seat order, no bids, no free reply.
    - Free bidding: highest bid speaks, no tokens spent, same tie-breaks, no free reply.
    - The three modes switch by setting only.
  - Verify: `uv run pytest tests/engine/test_day_modes.py -q`
  - Files: `engine/day.py`, `tests/engine/test_day_modes.py`
  - Depends on: T6

- [ ] **T8: Vote, win check, round limit, `play_game`** (M)
  - `engine/vote.py`, `engine/win.py`, `engine/game.py` (`play_game(seed, settings, agents) -> GameLog`).
  - Acceptance:
    - Sealed simultaneous votes with a one-line reason, revealed together; self-vote is illegal.
    - Most votes is removed; a tie removes nobody; abstain counts as no vote.
    - Village wins when both wolves are gone; wolves win when they equal or outnumber the rest; both checked after the morning and after each vote.
    - After round 6 with no winner, the village wins.
    - A whole game runs with scripted agents and returns a winner.
  - Verify: `uv run pytest tests/engine/test_vote.py tests/engine/test_win.py tests/engine/test_game.py -q`
  - Files: `engine/{vote,win,game}.py`, three test files
  - Depends on: T5, T7

### Checkpoint 2: Full game
- [ ] A scripted game plays start to finish with the right winner
- [ ] Every row in the plan's rule-to-test map has a passing test
- [ ] `check.ps1 task` passes and runs under 90 seconds
- [ ] Review with human before proceeding

## Phase 4: Replay and proof

- [ ] **T9: Game log and exact replay** (M)
  - `engine/log.py` (canonical JSON writer and `GameLog`), `engine/replay.py` (`replay(log)`), `.gitattributes`.
  - Acceptance:
    - The log holds seed, settings, roles, every event, every raw agent response (including rejected ones), failure counts and the winner.
    - Canonical: sorted keys, UTF-8, `\n` endings.
    - `replay(log)` reproduces a byte-identical log, including a game that contained a retry and a fallback.
    - A tampered log (changed seed or response) fails to match.
  - Verify: `uv run pytest tests/engine/test_replay.py -q`
  - Files: `engine/log.py`, `engine/replay.py`, `.gitattributes`, `tests/engine/test_replay.py`
  - Depends on: T8

- [ ] **T10: Scripted-game suite and CLI** (M)
  - A set of scripted games with known outcomes, and `werewolf.cli` with `play` and `replay`.
  - Acceptance:
    - Scripted games cover: village win by votes, wolf win by kills, round-limit village win, Doctor save changing the outcome, a fake-Seer claim, a game with rejected actions.
    - `uv run python -m werewolf.cli play --seed 1 --agents scripted` writes `data/games/<id>.json`; `replay` on that file reports an exact match.
    - Rejected-action rate and clean-game flag are printed per game.
  - Verify: `uv run pytest tests/scripted -q`; run the two CLI commands by hand.
  - Files: `src/werewolf/cli.py`, `agents/scripted.py` (extend), `tests/scripted/test_games.py`, `tests/scripted/test_cli.py`
  - Depends on: T9

- [ ] **T11: CI workflow** (S)
  - `.github/workflows/ci.yml` on every push: install uv, `uv sync --locked`, floor guard (`--base origin/main`), ruff, mypy, pytest.
  - Acceptance:
    - YAML is valid; every command in it runs locally.
    - No paid call, no secret needed.
    - Docker build left out (open question 1).
  - Verify: run each command locally; the first real run needs a GitHub remote.
  - Files: `.github/workflows/ci.yml`
  - Depends on: T10

### Checkpoint 3: before the gate
- [ ] Review with human before the gate run

- [ ] **T12: M1 gate** (S)
  - Run everything and write `docs/progress.md`.
  - Acceptance:
    - All rule tests, scripted games and the replay test pass.
    - Numbers recorded: test count, scripted games count, replay match, `check.ps1 task` runtime, ledger cap test result.
    - Coverage baseline recorded if `pytest-cov` is approved; otherwise noted as pending.
    - `CONSTRAINTS.md` "Measured" row updated with that baseline.
  - Verify: `powershell -File scripts/check.ps1 full`; a game replays exactly via the CLI.
  - Files: `docs/progress.md`, `CONSTRAINTS.md` (measured row only)
  - Depends on: T11
