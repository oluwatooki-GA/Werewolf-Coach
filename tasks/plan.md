# Implementation Plan: M1, setup and engine with no AI

Sources: `SPEC.md` (module `engine`), `docs/DESIGN.md` sections 2, 5.1, 5.4, 5.7, 7, `CONSTRAINTS.md`.
Tasks are tracked in `tasks/todo.md`. Plan written Oct 13, 2026.

## Overview

Build the full Werewolf game as plain, seeded Python with scripted fake agents, plus the cost ledger and CI. No model is called anywhere in M1. When it is done, a scripted 8-player game plays to a known winner, every rule has a test, and a game replays to a byte-identical log.

**Gate (DESIGN 10):** all rule tests and scripted games pass, and a game replays exactly. Numbers go in `docs/progress.md`.

## Dependency graph

```
bootstrap (pyproject, layout, architecture test)
   |
   +-- ledger (independent, stdlib)
   |
   +-- setup + state + views
          |
          +-- action layer (validate, retry, fallback) + scripted agents
                 |
                 +-- night phase
                 +-- day: floor tokens --> day: baselines
                 +-- vote + win check + round limit  ==> play_game (full game)
                        |
                        +-- game log + replay
                               |
                               +-- scripted-game suite + CLI
                                      |
                                      +-- CI --> gate
```

Public surface that later milestones depend on (kept small on purpose):
`play_game(seed, settings, agents) -> GameLog`, `replay(log) -> GameLog`, `make_view(state, player) -> PlayerView`, the `Agent` protocol (`async act(view, task) -> Action`), and `Ledger`.

## Architecture decisions

- **Layout:** `src/werewolf/engine/` (pure rules), `agents/scripted.py` (fake agents), `llm/ledger.py` (cost ledger). Matches SPEC.md.
- **Engine imports:** only the standard library, `pydantic`, and `werewolf.engine`. A stdlib `ast` test enforces this (allowlist, stronger than a banned list).
- **Public surface for agents:** `werewolf.engine.views` (`PlayerView`) and `werewolf.engine.actions` (`Task`, action models, `Agent` protocol). Agents import nothing else from the engine, so they cannot reach game state.
- **Determinism:** one `random.Random(seed)` owned by the game. No clock, no global random. Roles, seats and tie-breaks all draw from it in a fixed order.
- **Replay:** the log stores the seed, settings and every raw agent response in order, including rejected ones. `replay` feeds those responses back through a replay agent, so retries and fallbacks reproduce exactly. A replayed log must be byte-identical.
- **Canonical log:** JSON with sorted keys, `\n` line endings, UTF-8, so Windows and Linux CI agree. A `.gitattributes` pins `eol=lf` for JSON.
- **Retry and fallback (DESIGN 5.1):** a response that is broken or illegal gets one retry that includes the error text. A second failure uses the safe default (bid 0, abstain, no target) and counts as a rule-following failure. Agent exceptions count the same way. The engine never crashes on agent output.
- **Async:** engine is `async`; each speaking turn asks every living player at once with `asyncio.gather`. Tests use `asyncio.run`, so `pytest-asyncio` is not needed.
- **Ledger:** stdlib only. `Decimal` amounts (no float drift), per-key caps persisted to `data/ledger.json` with an atomic write, so the $4.50 cap holds across runs. Unknown keys fail closed. Free-tier keys have a cap of 0. It exposes `reserve` before a call and `settle` after. The LiteLLM wrapper that calls it is M2.
- **Action fields for later:** action models carry optional `note` and `beliefs` fields now, logged but unused in M1, so the log shape does not change at M2 (schema changes after M2 need your approval).
- **Storage:** M1 logs to JSON files under `data/games/`. Postgres is not in M1's list in DESIGN 10, so it waits (see open questions).
- **Dependencies:** only already-approved ones (`pydantic`; dev: `ruff`, `mypy`, `pytest`). Nothing else is added.

## Rule assumptions the plan makes (the design does not spell these out)

Correct any you disagree with before tasks 5 to 8.

1. Wolves cannot target a wolf; the Seer cannot check herself; the Doctor may protect herself and the same player on consecutive nights.
2. Wolf night order: wolf A speaks, wolf B speaks (sees A's message), then each submits a target. If they differ, the seeded rng picks one of the two.
3. Round = night, morning, day, vote. A win check runs after the morning announcement and after each vote.
4. Votes are sealed and simultaneous, revealed together. Voting for yourself is illegal. An abstain counts as no vote. Most votes is removed; a tie removes nobody. The role of anyone who dies stays hidden.
5. Floor tokens: public events are who spoke, what they paid, and who listened. Losing non-zero bids stay hidden. A bid above tokens left is illegal.
6. The free reply to an accusation counts as one of the 8 speaking turns, costs nothing, and goes to the named player only if alive. It exists in floor-token mode only.
7. Free-bid baseline: bids 0 to 4, no cost, highest speaks, same tie-breaks. Fixed-order baseline: living players speak in seat order, no bids.
8. Messages are capped at 300 characters (a setting).
9. Player names come from a fixed list (Ada, Bo, Cy, Di, Eve, Fay, Gus, Hal); the seed shuffles who gets which seat and role.

## Task list

### Phase 1: Foundation

- **T1** Project bootstrap, `.env` protection and architecture test
- **T2** Cost ledger

### Checkpoint 1: Foundation
Checks pass for real (ruff, mypy, pytest no longer "NOT RUN"), `.env` is ignored, the architecture test catches a planted violation, the ledger blocks at the cap.

### Phase 2: A game that can start and see

- **T3** Seeded setup, state and first player views
- **T4** Action layer: validation, retry, fallback, scripted agents

### Phase 3: Rules, one phase at a time

- **T5** Night phase
- **T6** Day discussion with floor tokens
- **T7** Day baselines (fixed order, free bidding)
- **T8** Vote, win check, round limit, `play_game`

### Checkpoint 2: Full game
A scripted game plays start to finish and ends with the right winner. Every rule in DESIGN 7.2 has a test.

### Phase 4: Replay and proof

- **T9** Game log and exact replay
- **T10** Scripted-game suite and CLI
- **T11** CI workflow

### Checkpoint 3: M1 gate
- **T12** Gate run and `docs/progress.md`

Full task detail with acceptance criteria and verification is in `tasks/todo.md`.

## Rule-to-test map (DESIGN 7.2, "unit tests for every rule")

| Rule | Task |
| --- | --- |
| Kills | T5 |
| Saves (including self-protect) | T5 |
| Seer checks | T5 |
| Bidding ties (least-spoken, then rng) | T6 |
| Zero bid is listening; all listening ends the day | T6 |
| Right of reply once per day | T6 |
| Unused tokens lost at nightfall | T6 |
| No overbidding | T6 |
| All randomness through the seeded rng | T6 |
| Vote ties | T8 |
| Win checks (both teams) | T8 |
| 6-round limit | T8 |
| Hidden information (no view holds another's role, wolf chat or Seer results) | T3, extended in T5 |
| Retry then safe default | T4 |
| Replay is exact | T9 |

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Floor-token rules are the most intricate part and easy to get subtly wrong | High | T6 comes right after the night phase, with a table-driven test for every tie case, written before the code |
| Log differs between Windows and Linux (line endings, key order, float formatting) | High | Canonical JSON writer, `.gitattributes`, and the replay test runs in CI on Linux |
| Replay breaks when an agent response was rejected and retried | High | Log stores every raw response in order; T9 has a replay test over a game that includes a retry and a fallback |
| `asyncio.gather` order changes results for real agents later | Med | The engine sorts responses by seat before resolving; T6 tests this with agents that answer in reverse order |
| CI cannot be verified without a GitHub remote | Med | T11 runs the same commands locally first; the real run waits for a push |
| Scope creep into M2 (prompts, beliefs, LiteLLM) | Med | Only optional `note` and `beliefs` fields are added; nothing calls a model |
| The architecture test is project-owned (circular) | Low | The allowlist is strict, it is tested against planted violations |

## Open questions (need your answer)

1. **Dockerfile in CI.** DESIGN 7.3 lists a Docker build in `ci.yml`, but the Dockerfile belongs to M7. Recommendation: leave the Docker build out of M1 CI and add it with the Dockerfile at M7.
2. **Coverage baseline.** `CONSTRAINTS.md` wants a coverage number recorded at this gate, which needs `pytest-cov` (not yet approved). Recommendation: approve `pytest-cov` as a dev dependency in T12.
3. **GitHub remote.** There is none yet. CI can be written but not run until you create the repo and push. Recommendation: create it before T11.
4. **Postgres timing.** Storage is not in M1. Recommendation: add the Postgres schema at M2 (it needs the turn fields M2 produces), so M1 stays JSON-only.
5. **Rule assumptions 1 to 9 above.** Any you want changed?
