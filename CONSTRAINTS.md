# Constraints

Last reviewed: 2026-10-13 by @Tooki. Source: docs/DESIGN.md sections 5.4 and 8, SPEC.md.
This file is the canonical bar. `scripts/check.ps1` mirrors it; if they differ, this file wins.
Failing checks block (decided Oct 13, 2026). Slowest allowed hand-back check: 90 seconds.

## Floor (always enforced)

- The engine never calls an LLM: `src/werewolf/engine/` imports no model, HTTP or network library, and no `werewolf.llm`, `agents` or `tagger` module.
- Agents only receive a `PlayerView`: code in `src/werewolf/agents/` may import from `werewolf.engine` only the public surface `werewolf.engine.views` and `werewolf.engine.actions`, never game state.
- Every paid model call goes through the cost ledger: only `src/werewolf/llm/` may import `litellm`, `openai` or `anthropic`.
- No new dependency without the owner's approval: a package in `pyproject.toml` must be listed in `.constraints/approved-deps.txt`, which only the owner edits.
- No new suppression comments in Python: `# noqa`, `# type: ignore`, `# pragma: no cover`, `# nosec`.
- No unimplemented stubs: `raise NotImplementedError`, `except ...: pass`, `TODO`.
- No skipped, xfailed or deleted tests, and no assertions removed from tests that stay.
- `.env` is git-ignored and never tracked (checked by the floor guard). There is no secrets scanner, so keys pasted into source are caught only by review.
- This file, `scripts/floor_guard.py`, `scripts/check.ps1`, and `.constraints/` are not weakened to make a change pass. Changes to them need the owner's approval.

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|-----------|------|-----------|---------|
| Floor | Zero violations (diff-scoped). Reason: the cheap road to green is the common agent failure. | `uv run --no-project python scripts/floor_guard.py` | every edit, task end, CI |
| Lint | Zero ruff errors. Reason: you required it. | `uv run ruff check .` | every edit |
| Types | Zero mypy errors in `src`. Reason: you required it. | `uv run mypy src` | every edit |
| Tests | All pass. Reason: you required it. | `uv run pytest -q` | task end, CI (under 90 s) |
| Architecture | The three import rules in the Floor hold. Reason: DESIGN 5.4 and 8 are structural, so a test beats review. | `uv run pytest tests/test_architecture.py -q` (stdlib `ast`, no new dependency) | task end, CI |

`tests/test_architecture.py` is an M1 deliverable. `scripts/check.ps1` fails once `pyproject.toml` exists and the file is missing.

Levels: `powershell -File scripts/check.ps1 fast` (floor, ruff, mypy; seconds), `task` (adds pytest), `full` (same as task; CI also runs the Docker build from `ci.yml`).

## Measured, not yet enforced

| Metric | Today | Direction |
|--------|-------|-----------|
| Line coverage, `engine/` and ledger | not measurable (no code) | record at M1's gate, then must not fall (0.5% tolerance). SPEC target stays 90%. |

Coverage tooling (`pytest-cov`) is added only after the owner approves it.

## Not set up

- Accessibility and web performance: no URL to run against until M7. Add axe-core and Lighthouse then.
- Dependency audit (osv-scanner) and Semgrep: not picked.

## Known gaps

- Until M1 task 1 creates `pyproject.toml`, `check.ps1` prints `NOT RUN` for ruff, mypy and pytest and exits 0. That lapses on its own once the file exists.
- The architecture and ledger rules rest on a project-owned test, which is the circular kind. There is no external check: the secrets scanner (gitleaks) was removed by the owner on Oct 13, 2026.

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|----|------|------|--------|-------|---------|
| none |  |  |  |  |  |
