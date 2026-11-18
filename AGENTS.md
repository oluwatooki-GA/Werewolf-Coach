# Werewolf Coach

AI agents play 8-player Werewolf from swappable strategy cards, and an AI coach writes better cards. Python engine, agents and API in `src/werewolf/`, a Next.js site in `web/`.

Build from `SPEC.md` (the build contract) and `docs/DESIGN.md` (the system design). After edits run:

```powershell
powershell -File scripts/check.ps1 fast
```

## Commands

Run from the repo root. Use uv for Python, never pip or poetry.

```powershell
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy src
cd web; npm test; npm run typecheck; npm run lint
```

`web/` is Next.js 16 with breaking changes from older versions. Read the guide in `web/node_modules/next/dist/docs/` before changing how it works.

## Rules that matter

- The engine in `src/werewolf/engine` never imports an LLM, and an agent only receives a `PlayerView`, never the game state. Tests enforce both.
- Every paid model call goes through the cost ledger, which stops at a cap per provider. CI never makes a paid call.
- Strategies live in `cards/` as YAML, never in code.
- A bug gets a failing test first. Do not remove or skip a failing test without the owner's approval.
- Keep keys in `.env`, which is git-ignored. Never commit a key.
- Plain language and sentence case in text and the UI. No em dashes.

## Ask the owner first

- Adding a dependency or a paid service.
- Changing the database schema, the card format, the move set or the CI files.
- Any run that spends real money beyond the plan, or raising a spend cap.
- Committing `.md` files other than `README.md` and this file.

## Commits

One short line, no milestone or task labels. Do not rewrite old commits. The owner pushes.
