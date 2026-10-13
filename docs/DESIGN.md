# Werewolf Coach: Design Document

Oct 12, 2026 · @Tooki

## 0. Read this first (for the AI building this)

This doc is the spec for Claude Code. Build in the milestone order in section 10, stop at each gate, and write the numbers into `docs/progress.md` before moving on.

**Rules for the builder:**

- **The game engine is plain code, never an LLM.** It owns the rules, the roles, who is alive, and what each player is allowed to see. Agents only choose words and actions; the engine checks every action.
- **No agent ever sees another agent's secret.** Each prompt is built only from that player's view. A CI test fails the build if a secret leaks.
- **Every game is fully logged and replayable** from its seed and log.
- **Strategies live in files, never in code.** A strategy card is a short text file with an ID and a version, so experiments can swap them freely.
- **Money is tight:** $5 of OpenAI credit and $5 of Claude credit in total, free tiers for testing. Every paid call goes through a cost ledger with a hard stop per provider (section 8).
- **No fine-tuning.** Plain language in the UI and README. No em dashes. Ask before adding a paid service.

### 0.1 Stack questions to ask Tooki before writing code

Ask these one at a time, give a recommended answer for each, and record the answers in `docs/decisions.md`.

1. **Player model for bulk games.** Decided: `gpt-4.1-nano`, measured at $0.015 per simulated game. Ollama is out: it runs on the CPU here at about 18 seconds a call.
2. **Paid models by job.** Recommended: `gpt-4.1-nano` for all bulk players and the caching experiment; Claude Haiku 5.5 for the tagger (batch API), the stronger-model games and live play; Claude Sonnet 5.5 for the coach and the tagger reference set.
3. **LLM client layer.** Recommended: LiteLLM, so OpenAI, Claude, Groq and Cerebras are called the same way and every call's tokens and cost are logged in one place. Groq and Cerebras free tiers are for smoke tests and E9 only.
4. **Game loop.** Recommended: plain async Python; the engine controls turns. No agent framework needed for the game itself.
5. **Coach agent framework.** Recommended: LangGraph, because the coach has real steps (read games, diagnose, write a card, check it) and may loop.
6. **Structured outputs.** Recommended: Pydantic models for every action, validated by the engine.
7. **Database.** Recommended: Postgres for games, turns and results; Parquet exports for analysis.
8. **Backend.** Recommended: FastAPI with WebSockets for live play.
9. **Frontend.** Recommended: Next.js with TypeScript.
10. **Hosting.** Recommended: Vercel for the site, Render or Fly.io for the API (one Docker service), Neon for Postgres. No AWS for now.
11. **Observability.** Recommended: Langfuse for LLM traces; structured JSON logs read in the host's log viewer.
12. **Package manager.** Decided: uv.

## 1. What Werewolf Coach is

Werewolf Coach is a lab where AI agents play Werewolf with different survival strategies, so we can find out which strategies work for each role, and whether an AI coach can invent better strategies than the ones humans write down.

### 1.1 The problem

AI agents increasingly deal with other agents: negotiating, persuading, and sometimes being lied to. We don't know much about which approaches work for an agent under social pressure, whether agents actually follow the strategy they're told to use, or whether they can learn better ones from experience. Werewolf is a small, safe, measurable place to study all three: every player has a hidden goal, lying is part of the game, and the result (who survived, who won) is clear.

### 1.2 What we study

1. **Which strategy works for each role?** For example, is a quiet wolf or a loud accusing wolf more likely to survive? Should the Seer reveal early or stay hidden?
2. **Do agents actually play the strategy they're given?** We check what their messages really do (accuse, defend, question...), not what the card says.
3. **Can an AI coach invent better strategies?** A coach agent studies lost games and writes new strategy cards. Do its cards beat the human-written ones?
4. **Can agents spot and counter a strategy?** For example, do villagers catch a wolf who falsely claims to be the Seer?

### 1.3 What we borrow from the two papers

| Paper | What they did | What Werewolf Coach uses |
| --- | --- | --- |
| Werewolf Arena (Google, 2024) | A code game master running 8 AI players; agents bid 0 to 4 for how urgently they want to speak; agents keep summarised memories; votes come with reasons; tournaments between models | The 8-player setup, memory summaries and reasoned votes. Their free 0 to 4 bid is kept only as a baseline for this project's own floor-token bidding (2.2) |
| Werewolf Among Us (2023) | Tagged every line of real human games with 6 persuasion moves: claiming an identity, accusing, questioning, calling for action, defending, giving evidence | The idea of tagging persuasion moves. Werewolf Coach uses its own move set (3.5), with a target and a true-or-false check on every claim, which tags on human videos can't give |

Werewolf Coach doesn't try to reproduce their results. It reuses their methods to answer a different question: which strategies keep an agent alive, and can agents discover better ones?

## 2. The game

Same setup as Werewolf Arena, so results are comparable in spirit, with short messages to keep games cheap and fast.

### 2.1 Roles (8 players)

| Role | How many | Team | Power |
| --- | --- | --- | --- |
| Werewolf | 2 | Wolves | Each night the wolves agree on one player to kill. They know each other. |
| Seer | 1 | Village | Each night, learns the true role of one player. |
| Doctor | 1 | Village | Each night, protects one player from being killed. |
| Villager | 4 | Village | No power. Reasons and votes. |

### 2.2 A round

1. **Night:** wolves agree on a target (one private message each, then a target choice); the Seer checks someone; the Doctor protects someone. The engine resolves it.
2. **Morning:** the engine announces who died. Roles of the dead stay hidden.
3. **Day discussion, with floor tokens:** each living player starts the day with 3 floor tokens. Every speaking turn, each player sends one sealed bid (0 to 3 tokens), the message they'd say, and a private intent with a target (accuse, defend, share info, ask). The highest bid speaks and pays what it bid; ties go to whoever has spoken least today, then at random. A bid of 0 means listening, and the chat shows it ("Ada is listening"). If the posted message accuses someone by name (read from the speaker's intent and target), that player gets one free reply next, once per day. Unused tokens are lost at nightfall. Repeat for 8 speaking turns, or stop early when everyone listens. One call per player per turn gives the bid, message and intent together.
4. **Vote:** every living player votes to remove one player, with a one-line reason. Most votes is removed; a tie removes nobody.
5. **Win check:** the village wins when both wolves are gone; the wolves win when they equal or outnumber the rest. Hard limit of 6 rounds, then the village wins.

Speaking rules are a setting: fixed order, free bidding (Werewolf Arena's 0 to 4 with no cost) or floor tokens. The first two are baselines for E6. Floor tokens make talking cost something, so when an agent speaks and when it saves up tells you something about it.

### 2.3 Scope

- **In:** AI-only games, a human seat in the app, strategy cards, the coach, analysis, an open dataset of logs.
- **Out for v1:** extra roles, more than 8 players, voice, any fine-tuning.

## 3. Strategies

Every agent gets its role plus one **strategy card**: a short instruction for how to play that role. Experiments assign cards to seats, so we can compare them fairly.

### 3.1 What a card looks like

```yaml
id: wolf.lie_low
version: 1
role: Werewolf
source: community guide
summary: Stay unnoticed and let the village tear itself apart.
instructions: >
  Speak rarely and bid low. Agree with whoever the majority suspects.
  Never accuse first. If accused, stay calm and point to your voting record.
expected_moves: [hedge, self_defend, record_check]   # from the move set in 3.5
```

Cards are 80 words or fewer, may only mention things the player can know, and list the persuasion moves they expect, so the tagger can check whether the agent follows them.

### 3.2 Starter cards (3 per role for v1, 5 per role later)

| Role | Card 1 | Card 2 | Card 3 | Later |
| --- | --- | --- | --- | --- |
| Wolf | Lie low and follow the majority | Accuse early and loudly | Falsely claim to be the Seer | Vote out your own partner to look innocent; pin it all on one quiet player |
| Villager | Quiet observer | Ask pointed questions | Track who changes votes | Follow whoever claims Seer; make everyone explain their votes |
| Seer | Reveal right away | Stay hidden and drop hints | Reveal only when a checked wolf is about to escape |  |
| Doctor | Protect yourself | Protect whoever claims Seer | Protect the loudest villager |  |

### 3.3 Where strategies come from

1. **Community strategy guides.** Werewolf and Mafia players have written up common strategies for years (the Mafiascum wiki is the largest). We summarise ideas into our own short cards, credit the source in each card, and never copy text.
2. **The project's move set** (3.5), used to describe what each card should make the agent do.
3. **The coach agent** (3.4), which writes new cards from game evidence.

### 3.4 The coach agent (strategy discovery)

After a batch of games, the coach tries to improve one role's strategy:

1. **Read:** the games where that role lost, with each player's tagged moves, votes and private notes.
2. **Diagnose:** write down why they lost, with evidence ("wolves who accused in round 1 were voted out next round in 7 of 10 games").
3. **Write a challenger card** that fixes the problem, in the same format.
4. **Check it:** code checks the length and format; an LLM check confirms it doesn't rely on hidden information or break the rules.
5. **Test it:** the challenger plays a batch against the current best card (the champion) on the same seeds. If it wins clearly more often, it becomes the new champion. Otherwise it's logged and dropped.

The coach runs on Claude Sonnet 5.5 because it needs better reasoning, but it only runs a few times per experiment. Every generation's card, diagnosis and result is saved, so the README can show how strategies evolved.

### 3.5 Persuasion moves

Werewolf Coach tags every public message with its own move set, built around the decisions in this game. Each tag has three parts: the move, the target player, and for claims, whether it was true. The engine knows every hidden role, so truth is checked in code.

| Family | Move | Example line | Honest use vs wolf use |
| --- | --- | --- | --- |
| Claims | `role_claim` | "I'm the Seer." | Real Seer reveals to steer votes; wolf fakes it to take control |
| Claims | `result_claim` | "I checked Bo last night. Wolf." | Checked against the night log, so a lie is caught automatically |
| Claims | `record_check` | "Cy switched his vote at the last second yesterday." | Cites the public log; wolves cite it selectively |
| Pressure | `accuse_reasoned` | "Di defended Bo twice, then went quiet." | Villagers build a case; wolves frame someone |
| Pressure | `accuse_bare` | "I just think it's Eve." | Low effort; tests whether bare accusations ever work |
| Pressure | `probe` | "Fay, who would you vote for and why?" | Testing someone vs fishing for the Seer |
| Protection | `self_defend` | "I voted with the majority both days." | Everyone does it; how strong it sounds is the tell |
| Protection | `vouch` | "I trust Gus, he's been consistent." | Villager trust vs a wolf shielding its partner |
| Steering | `rally` | "Everyone, vote Bo now." | Closing a case vs rushing a vote before questions come up |
| Steering | `redirect` | "Forget Bo, look at Cy." | Fresh evidence vs pulling heat off a partner |
| Steering | `hedge` | "Let's not rush, we don't know enough." | Real caution vs stalling |

A message gets one or two moves. Silence isn't tagged from text: a bid of 0 is stored as listening (2.2).

**Derived labels.** After tagging, the engine adds these from the hidden roles, with no model call. The tagger never sees them.

- `lie`: a claim the engine knows is false.
- `fake_claim`: a wolf claiming Seer or Doctor.
- `counter_claim`: a second player claiming a role someone already claimed.
- `bus`: a wolf accusing or voting for its own partner.
- `shield`: a wolf vouching for its own partner.
- `hit`: an accusation that lands on a real wolf, from any role.

A stored tag looks like this:

```json
{"turn": 14, "speaker": "Cy", "move": "result_claim", "target": "Bo",
 "claimed": {"role": "Seer", "checked": "Bo", "result": "wolf"},
 "true": false, "derived": ["lie", "fake_claim"]}
```

Most findings come from the derived labels, for example how long wolves survive after busing their partner on day 1.

## 4. How it fits together

&#91;embedded content: Tells architecture · one game, and the coach loop between batches\]

Each agent plays from its role and strategy card, sees only its own view, and the engine checks every action. Between batches, the tagger labels every message, and the coach reads the losing games and writes a new card, which replaces the old one only if it wins its test. All model calls go through one LLM layer (LiteLLM) that handles OpenAI, Claude, free-tier providers, caching and cost tracking; the web app replays games and shows the strategy board.

## 5. Components

### 5.1 Game engine (plain code)

- Holds the true state: roles, who's alive, night actions, bids, votes, round number.
- Runs each phase, asks the right players for actions, checks every action is legal, and resolves results.
- Builds each player's **view**: only what that player may know. This is the only way information reaches an agent.
- Seeded randomness (roles, seats, tie-breaks), so any game replays exactly, and two strategies can be compared on the same seeds.
- Broken or illegal output: one retry with the error message, then a safe default (bid 0, abstain), logged as a rule-following failure.

### 5.2 Player agents

Each turn, every player:

1. **Observes** its view (new messages, deaths, its own night results).
2. **Updates beliefs:** a small table of suspicion (0 to 1) for each other player, with a one-line reason.
3. **Thinks privately:** a short note, logged but never shown to others.
4. **Acts:** returns one structured action (bid + message + intent, vote + reason, or night target), checked against a Pydantic schema.

The prompt contains: the fixed rules, its role, its **strategy card**, its belief table and memory, the public log, and the task. Steps 2 to 4 happen in one model call to keep games cheap.

### 5.3 Memory

- **Public log:** every posted message, death and vote, append-only.
- **Private memory:** the belief table plus a short summary of older rounds, rewritten at the end of each round, so prompts stop growing after round 2.

### 5.4 Hidden information

- Wolves' night chat goes only to wolves; the Seer's result only to the Seer; private notes go to no one.
- **Leak test (CI):** plant a code word as a wolf's secret, play a scripted game, and fail if the word appears in any non-wolf prompt.
- Claiming a role out loud is allowed; it's a strategy, and it's counted.

### 5.5 Move tagger

- Labels each public message with one or two moves from 3.5, the target player, and for claims, the claimed fact as fields (claimed role, who was checked, the result, the vote cited).
- The engine then adds the true-or-false check and the derived labels from the hidden roles. No model call is needed for those.
- Claude Haiku 5.5 tags every message through the batch API (half price, results within a day). Claude Sonnet 5.5 tags a 300-message reference set; agreement is reported per move, and only the messages where they disagree (about 40) are checked by hand.
- Used to check strategy adherence (does a "lie low" wolf actually avoid accusing?), to compare each message with the speaker's own intent from its bid, and to feed the coach.

### 5.6 Caching

- **Prompt layout built for caching:** fixed rules and strategy card first, then the public log, then private memory, then the task. On OpenAI, the long unchanged start is cached automatically and billed at a discount; the speed test measures how much.
- **Response cache:** every call is stored by a hash of its full prompt and settings. Re-running an analysis or a replay never pays twice, and identical calls in repeated experiments are reused.
- **Tagger cache:** each message is tagged once, keyed by its text hash.
- **Replay cache:** finished games are never re-run; the app replays from logs.
- Cost and cached-token share are logged per call and per game.

### 5.7 Storage

- **Postgres:** games (seed, settings, cards, winner), seats (model, role, card, survival), turns (bid, tokens left, intent, message, private note, beliefs, action, tags, tokens, cost), coach generations, human sessions.
- **Files:** full game logs as JSON in Postgres; Parquet exports in a git-ignored `data/` folder, published as an open dataset on Hugging Face.

### 5.8 API and frontend

- FastAPI: `POST /games`, `GET /games/{id}`, `WS /play/{id}`, `GET /strategies`, `GET /results`, `GET /health`, `GET /metrics`.
- Next.js app:
  - **Replay viewer:** chat timeline with each message's bid and persuasion tags; toggle each agent's private note, suspicion table and strategy card.
  - **Strategy board:** win and survival rates per card, and the coach's family tree of cards with its diagnoses.
  - **Play mode:** take one seat against the agents, with a turn timer.

### 5.9 MCP server

Exposes `start_game`, `get_game`, `list_strategies` and `get_results` as tools, with an API key and a rate limit.

## 6. Experiments

All bulk experiments run on one player model, `gpt-4.1-nano`. Each compares strategies on the **same seeds** (same roles and seats), so a difference comes from the strategy, not luck. Sizes below fit the budget in section 8. Pooled across its opponents, each E1 card plays 18 games, so only big gaps (roughly 25 points of win rate or more) will be clear; every result is reported with its interval.

| # | Experiment | Setup | What we measure |
| --- | --- | --- | --- |
| E1 | Wolf vs villager strategies | 3 wolf cards x 3 villager cards, Seer and Doctor on a default card, 6 games per pairing (54 games) | Wolf team win rate, rounds each wolf survives, share of votes that land on wolves |
| E2 | Seer and Doctor strategies | 3 Seer cards and 3 Doctor cards, 6 games each, everything else default (36 games) | Village win rate, Seer survival, Doctor saves |
| E3 | Do agents follow their card? | The move tagger over every game from E1 and E2 | Share of turns matching each card's expected moves and the speaker's own intent; which cards models ignore |
| E4 | Can the coach do better? | 2 coach generations for wolves and 2 for villagers; each challenger plays 10 games against the champion on the same seeds (40 games) | How often challengers beat the human-written cards, and what the coach changed |
| E5 | Spotting a fake Seer | Games where one wolf uses the fake-Seer card (from E1) | How often villagers vote out the fake vs the real Seer, and how many rounds it takes |
| E6 | Speaking rules | Fixed order vs free bidding vs floor tokens, 10 games each with default cards (30 games) | Village win rate, rounds until the first wolf is voted out, how often agents repeat themselves, and token spending by role (do wolves hoard, do real Seers save up for the reveal?) |
| E7 | Small model vs stronger model | 20 games on Claude Haiku 5.5 with the best E1 cards | Whether the winning strategies stay the same with a stronger model |
| E8 | Who lies, and does it work? | The derived labels (3.5) over every game from E1, E2, E4 and E6, no new games | Lie rate by role and card, share of lies caught (liar voted out within a day), bus and shield rates vs wolf survival |
| E9 | Another model family | 10 games on gpt-oss-120b through the Groq or Cerebras free tier: the best and worst E1 pairings, 5 each, spread over a few days | Whether the E1 ranking holds on a different family of model |

### 6.1 How results are judged

- Every win rate is shown with a margin of error. With 10 games a pairing, differences under about 30 points are flagged as "not clear yet".
- A strategy is called better only when it wins clearly more often than the other on the same seeds. Close calls get more games before any claim.
- Rule-breaking and fallback actions are reported for every card and model, because a strategy that "wins" by confusing a weak model isn't a real result.
- All findings are about these agents in this game, not about deception in general.

## 7. Evals, tests and CI/CD

Two kinds of checks: does the engine work (tests), and do the agents behave properly (evals). Results live in `evals/results/` as committed JSON.

### 7.1 Evals

| What | How it's measured | Target or baseline |
| --- | --- | --- |
| Rule following | Share of actions the engine rejects; share of games finished without a fallback | Under 2% rejected; 95%+ clean games |
| Secrets kept | Leak test; agents stating facts they couldn't know | 0 |
| Play quality | Village win rate, votes landing on wolves | Better than random voting and "vote the loudest player" bots |
| Strategy adherence | Tagged moves vs each card's expected moves | Reported per card and model |
| Tagger accuracy | You label 100 messages; compare the OpenAI and local taggers to your labels | Agreement reported; the local tagger is only used if it's close |
| Reasoning matches action | Vote matches the private note (code check) | Reported per model |
| Coach validity | Share of coach cards that pass the checks in 3.4 | Reported per generation |
| Cost and speed | Seconds and dollars per game; cached-token share | Caching on vs off on the same 5 OpenAI games |

### 7.2 Tests

- Unit tests for every rule: kills, saves, Seer checks, bidding ties, vote ties, win checks, the round limit.
- Scripted games with fake agents whose result is known in advance.
- Leak test, replay test (same seed and log give the same game), and strategy card format checks.
- Integration test: one full game with recorded model responses, so CI runs offline and free.

### 7.3 CI/CD (GitHub Actions)

- **`ci.yml`, every push:** lint (ruff), types (mypy), unit tests, scripted games, leak and replay tests, Docker build.
- **`eval-check.yml`, pull requests that change prompts, cards or agent code:** replays a fixed set of recorded games and fails if rule-breaking rises or adherence drops; posts a before-and-after table. No paid calls in CI.
- **`release.yml`, version tags:** build the Docker image, migrate, deploy to the host, log a deploy marker.

## 8. Models and budget

You have $5 of OpenAI credit, $5 of Claude credit, and the Groq and Cerebras free tiers. One player model, `gpt-4.1-nano`, plays all bulk games so results compare; Claude does the jobs that need a stronger model.

### 8.1 Who uses what

| Job | Model | Rough cost |
| --- | --- | --- |
| All players in E1, E2, E4 and E6, about 160 games | `gpt-4.1-nano`, cached | about $4.00 |
| Caching experiment, 5 games on and 5 off | `gpt-4.1-nano` | about $0.20 |
| Move tagger on every message | Claude Haiku 5.5, batch API | about $0.50 |
| Tagger reference set, 300 messages | Claude Sonnet 5.5, batch API | about $0.35 |
| Coach agent, 4 generations | Claude Sonnet 5.5, cached | about $1.00 |
| Stronger-model games (E7), 20 games | Claude Haiku 5.5, cached | about $0.50 |
| Live play mode on the site ($0.10 a day, $1 in total) | Claude Haiku 5.5 | up to $1.00 |
| Other model family (E9), 10 games | `gpt-oss-120b` on Groq or Cerebras free tier | $0 |
| Smoke tests while building | Groq or Cerebras free tier | $0 |
| **Total** |  | **OpenAI about $4.20, Claude about $3.35** |

The cost ledger stops paid calls at $4.50 per provider, so a bug can't empty either account. The table plans on $0.025 a game: the speed test measured $0.015 with short prompts, and real games carry more chat history. Re-measure on M2's first 10 real games and resize the experiments before running them. This uses nearly all the OpenAI credit, so Night Shift will need its own.

Building costs almost nothing. Rule and engine tests use scripted fake agents; prompt work runs on the Groq or Cerebras free tier; the response cache makes re-running a recorded game free. One game is about 112 calls and 170K input tokens, and Groq's free plan lists about 200K tokens a day per model, so that's roughly one free game a day there (check your account's limits page). Cerebras allows about 1M tokens a day.

### 8.2 Speed test results

| Model | Seconds per call | Valid JSON | Per game |
| --- | --- | --- | --- |
| `gpt-4.1-nano` | 1.7 | 100% | about 3 minutes, $0.015 |
| `llama3.2:3b` on Ollama (CPU only) | about 18, rising to 34 as the chat grew | 100% | well over 30 minutes |

Ollama is dropped: with no GPU, the time grows with prompt length and a full game takes over half an hour. Only 29% of `gpt-4.1-nano` input hit the cache because OpenAI caching is best effort; send one game's calls in order with the same prefix, and try the `prompt_cache_key` parameter.

### 8.3 Run time

About 160 games at 3 minutes each is 8 hours one at a time. Running 4 games in parallel brings a full set to about 2 hours, if your OpenAI rate limits allow it (check the limits page).

## 9. Deployment, observability and hooks for Night Shift

Experiments run from your machine against the model APIs. The deployed app serves replays, the strategy board and live human games.

| Part | Where | Notes |
| --- | --- | --- |
| Website (Next.js) | Vercel | Free tier |
| API and game server (FastAPI + WebSockets) | Render or Fly.io, one small Docker service | Same image runs locally |
| Database | Neon Postgres | Free tier; branch per pull request if needed |
| Open dataset | Hugging Face Datasets | Parquet, public |
| Secrets | The host's environment variables and GitHub Actions secrets | No keys in code |
| Infra | `Dockerfile` plus `render.yaml` or `fly.toml` | One command to deploy |

Spend limits are set on the OpenAI and Claude consoles on day one. Live play (one human joins a game against 7 AI players on the site) uses Claude Haiku 5.5, as in 8.1, capped at $0.10 a day and $1 in total; when a cap is hit, play mode pauses and replays keep working.

- **Langfuse:** every model call traced with game, seat, role, card, tokens, cached tokens and cost.
- **Logs and counts:** structured JSON logs with the game ID, read in the host's log viewer; games started and finished, rejected actions, fallbacks, WebSocket errors and cost per day kept in Postgres and shown on an admin page.
- **Night Shift hooks:** `/health` (database, model provider, game server), deploy markers, test-only fault switches (a model that times out, broken JSON, a game that never ends, a retry loop burning tokens), and `docs/runbook.md`.

## 10. Milestones and your part

Each milestone ends with numbers in `docs/progress.md`. Don't start the next until the gate passes.

1. **M0, speed test:** done (8.2). Ollama dropped; `gpt-4.1-nano` picked as the player model.
2. **M1, setup and engine with no AI:** repo, uv, CI, cost ledger, the full rules with bidding, views, logging, replay, scripted fake agents. Gate: all rule tests and scripted games pass; a game replays exactly.
3. **M2, real agents:** player prompts, structured actions, belief tables, memory, caching layout, response cache, leak test. Gate: 10 gpt-4.1-nano games with under 2% rejected actions and no leaks; real cost per game written into 8.1.
4. **M3, strategy cards and tagger:** the 12 starter cards, card checks, local and OpenAI taggers, your 100 labels. Gate: tagger agreement reported; cards load and swap without code changes.
5. **M4, experiments E1 to E3, E5, E6:** overnight runs, exports. Gate: every pairing has its planned number of clean games.
6. **M5, the coach (E4):** the LangGraph coach, champion vs challenger runs, generation history. Gate: 3 generations per side completed and logged.
7. **M6, extra runs (E7, E9 and caching):** E7 on Claude Haiku 5.5, E9 on the Groq or Cerebras free tier, and the caching experiment on `gpt-4.1-nano`. Gate: results committed; spend still under the ledger caps.
8. **M7, app and deploy:** replay viewer, strategy board, play mode, deploy, Langfuse, logs, health check, fault switches. Gate: a tagged release deploys with no manual steps and a human can finish a game.
9. **M8, ship:** README as a product spec, findings write-up, open dataset, demo video.

### What only you can do

- [ ] Run the speed test and pick the model.
- [ ] Write or approve the 12 starter cards (read a few community strategy articles first).
- [ ] Hand-check the messages where the two taggers disagree (about 40).
- [ ] Play 5 games yourself against the agents and note what feels wrong.
- [ ] Read the coach's diagnoses for each generation and check they make sense.
- [ ] Create the Vercel, Render (or Fly.io), Neon and Langfuse accounts, and the OpenAI and Claude keys with spend limits.
- [ ] Write the findings in your own words.
- [ ] Open at least one real issue or PR upstream (LiteLLM, Langfuse or another library you use) for a problem you hit.
- [ ] Record the demo video.

## 11. Risks, README, demo and first prompt

### 11.1 What could go wrong, decided now

| Risk | Fix |
| --- | --- |
| Real games cost more than planned | Re-measure on M2's first 10 games and shrink experiment sizes before running them |
| Small model too weak to follow strategies (all cards play the same) | E3 measures it. If adherence is low, say so, rely more on E7 (Claude Haiku 5.5) for strategy claims |
| Broken JSON or illegal moves | Structured outputs, one retry, then a safe default; counted, never a crash |
| Secrets leak between agents | Views built only by the engine, plus the leak test in CI |
| Too few games for clear results | Same seeds for fair comparisons, margins of error on every number, "not clear yet" labels, extra games only for close calls |
| Coach writes useless or cheating cards | Format and rule checks before any game; every generation is tested against the champion |
| Running out of credit | Cost ledger hard stop at $4.50 per provider; response cache so re-runs are free; free tiers and scripted agents for all testing |
| Copying community guides | Summarise ideas in our own words, credit the source in each card |
| Scope creep | 3 cards per role, 8 players, fixed rules; anything else goes on a "later" list |

### 11.2 README headline numbers (filled with real results)

- "Across N games, wolves who lie low survived X rounds longer than wolves who accuse early."
- "Agents followed their strategy card in Y% of turns; small models ignored the fake-Seer card most often."
- "After 3 generations, the coach's wolf strategy won Z% of games against the best human-written card."
- "Villagers caught a fake Seer in W% of games."
- "Prompt caching cut the cost of a game from $A to $B; N games played and every message tagged for under $8 in total."

### 11.3 The two-minute demo

1. The strategy board: which cards win for each role.
2. A replay: a fake-Seer wolf at work, with its private note and card shown next to its public lies.
3. The coach's family tree: a losing card, the coach's diagnosis, the new card, and its win rate.
4. Join a live game as a villager and try to catch the wolves.
5. The Langfuse trace for one game: calls, cached tokens, cost.

### 11.4 Suggested first prompt for Claude Code

This uses the agent-skills commands (`/spec`, `/constraints`, `/plan`, `/build`, `/test`, `/review`). First save this doc as `docs/DESIGN.md`, then run these in order:

```text
/spec Write SPEC.md from docs/DESIGN.md (Werewolf Coach). The design is decided, so don't redesign it. List your assumptions, then ask me the stack questions in section 0.1 one at a time, each with your recommendation. Use the milestones in section 10 as the capability map. Boundaries: Windows, PyCharm, uv only, keys in .env, no AWS.
```

```text
/constraints From docs/DESIGN.md sections 5.4 and 8: the engine never calls an LLM; agents only receive a PlayerView, never the game state; every paid model call goes through the cost ledger; no new dependency without asking me; ruff, mypy and pytest must pass.
```

```text
/plan Milestone M1 only (section 10 of docs/DESIGN.md). The last task is M1's gate.
```

Then `/build` for the first two or three tasks, `/build auto` for the rest once you trust it, and `/test` and `/review` at the end. For each later milestone, start again at `/plan` with that milestone's number.

## Sources

- [Werewolf Arena: A Case Study in LLM Evaluation via Social Deduction (arXiv)](https://arxiv.org/abs/2407.13943v1)
- [Werewolf Among Us: Multimodal Resources for Modeling Persuasion Behaviors in Social Deduction Games (arXiv)](https://ar5iv.labs.arxiv.org/html/2212.08279)
- Mafiascum wiki: community Mafia and Werewolf strategy articles (check the site's terms; summarise, don't copy).
