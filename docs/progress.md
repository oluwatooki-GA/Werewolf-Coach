# Progress

Numbers for each milestone gate (DESIGN section 10). A gate passes before the next milestone starts.

## M1: setup and engine with no AI (Oct 13, 2026)

**Gate (DESIGN 10): all rule tests and scripted games pass, and a game replays exactly. Result: passed.**

| Check | Result |
| --- | --- |
| Total tests | 207 passed, 0 skipped, 0 failed |
| `check.ps1 full` (floor guard, ruff, mypy, pytest) | passes, 12 seconds end to end (budget: 90) |
| Scripted games with known outcomes | 6 scenarios, all end as worked out by hand (winner and round) |
| Replay | exact (byte-identical log) for all 6 scripted games, all 3 speaking modes, seeds 1 to 3, and a game with retries, a crash and fallbacks |
| Real run by hand | `play --seed 1 --agents scripted` then `replay`: "exact match" |
| Cost ledger | blocks at the $4.50 cap (exact cap allowed, one cent over blocked), fails closed on unknown providers and corrupt files, 17 tests |
| Architecture test | 15 tests; each rule is also proven against a planted violation |
| Hidden information | 25 leak tests (6 seeds x 4 checks, plus a played night): no view holds another player's role, the wolf chat or Seer results |
| Line coverage, `engine/` and ledger | 98.5% (599 of 608 statements); SPEC target is 90% |
| Model calls made | 0. Money spent: $0.00 |

Uncovered lines are defensive type guards (an answer that is not a bid or a vote). The coverage baseline must not fall (CONSTRAINTS.md).

### Tests by area

| Area | Tests |
| --- | --- |
| Architecture rules | 15 |
| Ledger | 17 |
| Setup and seeding | 8 |
| Views | 7 |
| Leak tests | 25 |
| Actions: retry, fallback | 13 |
| Night | 17 |
| Day with floor tokens | 16 |
| Day baselines | 14 |
| Vote | 9 |
| Win check, round limit | 8 |
| Whole games | 12 |
| Log and replay | 16 |
| Scripted-game suite | 22 |
| CLI | 8 |

### Rule-to-test map (from the plan)

Every row has passing tests: kills, saves (including self-protect), Seer checks, bid ties, zero bid is listening, all listening ends the day, right of reply once per day, tokens lost at nightfall, no overbidding, all randomness through the seeded RNG, vote ties, win checks for both teams, the 6-round limit, hidden information, retry then safe default, exact replay. The seven named T6 tests are in `tests/engine/test_day_tokens.py`.

### Things that differ from the plan, or that you should know

- **Not run yet: CI.** `.github/workflows/ci.yml` is written and every command in it passes locally, but there has been no push, so GitHub has not run it. Against `origin/main` today the floor guard flags the three bar files as edited, because the remote only has the initial commit. After `main` is pushed the base equals HEAD and it is clean. A branch or PR that edits `scripts/`, `.constraints/` or `CONSTRAINTS.md` rules will fail the guard on purpose, until you approve it.
- **No Docker build in CI** (deferred to M7 with the Dockerfile) and **no Postgres** (planned for M2). M1 saves games as JSON files in `data/games/`.
- **No secrets scanner.** gitleaks was removed at your request. `.env` is git-ignored and the floor guard fails if it is ever tracked.
- **`play_game` returns the final `GameState`**, and `to_log(state)` builds the `GameLog`. SPEC.md was updated to match.
- **`Role` is exported by `engine.views`**, because a `PlayerView` shows the player's own role and the scripted agents need to compare it. The architecture rule itself was not changed.
- **`BidTask` has a `free` flag**, so an agent can tell a free turn (fixed order, or a reply) from a bidding turn.
- **A hidden `NightSummary` event** records the real kill, protection and Seer check (audience: nobody) for later analysis. It never reaches a view, and a test checks that.
- **Action models carry optional `note` and `beliefs` fields** now, unused in M1, so the log shape does not change at M2.
- **`pytest-cov` was added** (your approval; its own commit). `ruff format` was applied to the codebase.
- The rule assumptions in `tasks/plan.md` (1 to 9) were all built as written.

### Needs you

- Push `main` when you want CI to run for real. The `origin` remote is already attached; nothing has been pushed.
- Add an `OPENAI_API_KEY` to `.env` before M2 (only `ANTHROPIC_API_KEY` is there today).
- Read the nine rule assumptions in `tasks/plan.md` once more: they are now fixed in code and tests.
