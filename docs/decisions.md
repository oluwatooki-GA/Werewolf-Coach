# Decisions

Answers to the stack questions in DESIGN.md section 0.1. Dated Oct 13, 2026.

| # | Question | Decision |
| --- | --- | --- |
| 1 | Player model for bulk games | `gpt-4.1-nano` (decided in the design). Ollama is out. |
| 2 | Paid models by job | `gpt-4.1-nano` for bulk players and the caching test. Claude Haiku 5.5 for the tagger (batch API), E7 and live play ($0.10 a day, $1 in total). Claude Sonnet 5.5 for the coach and the tagger reference set. |
| 3 | LLM client layer | LiteLLM. If it can't drive Anthropic's batch API, use the anthropic SDK for the tagger batch job only, still through the cost ledger. |
| 4 | Game loop | Plain async Python. The engine controls turns. |
| 5 | Coach framework | LangGraph, added at M5 only. |
| 6 | Structured outputs | Pydantic models per action. The engine validates schema and game legality. |
| 7 | Database | Postgres in Docker locally, Neon at M7 by changing `DATABASE_URL`. Parquet exports for analysis. |
| 8 | Backend | FastAPI with WebSockets (M7). |
| 9 | Frontend | Next.js with TypeScript in `web/` (M7). npm by default, since uv covers Python only. |
| 10 | Hosting | Vercel (site), Fly.io (API, `fly.toml`), Neon (Postgres). No AWS. Check current free-tier terms at M7 and ask before anything costs money. |
| 11 | Observability | Langfuse through the LiteLLM callback, plus structured JSON logs. |
| 12 | Package manager | uv (decided in the design). |

## Resolved conflicts in the design

- Live play model: Haiku 5.5 (8.1 and 9 now agree).
- "Local tagger" in 7.1 and M3: there is no local tagger, because Ollama is dropped. Tagger accuracy compares the Haiku tagger and the Sonnet reference set against the 100 hand labels.
