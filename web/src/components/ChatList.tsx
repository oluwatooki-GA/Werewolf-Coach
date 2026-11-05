"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { GameSummary } from "@/lib/api";
import { plural } from "@/lib/format";
import { modelLabel, modelsIn, SORTS, sortGames, type SortId } from "@/lib/models";
import { ChatAvatar } from "./ChatAvatar";
import { TeamMark } from "./TeamMark";
import { Waker } from "./Waker";
import styles from "./ChatList.module.css";

type Props = {
  games: GameSummary[];
  total: number;
  /** The API did not answer, so `games` is the hand-picked set saved in the site, not the whole list. */
  down?: boolean;
};

const PINNED = [
  { href: "/welcome", match: "/welcome", kind: "welcome", title: "Werewolf Coach", line: "Start here: what this is" },
  { href: "/board", match: "/board", kind: "strategies", title: "Strategies", line: "The strategy cards and how each did" },
  { href: "/coach/wolf", match: "/coach", kind: "coach", title: "Coach", line: "The AI that rewrites the strategies" },
  { href: "/play", match: "/play", kind: "play", title: "Play", line: "Pick the cards, watch the agents play" },
] as const;

type Filter = "all" | "Wolves" | "Village";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Any" },
  { id: "Wolves", label: "Wolves" },
  { id: "Village", label: "Village" },
];

/** The list of chats on the left: the pinned ones, then every saved game, sorted as the reader chooses. */
export function ChatList({ games, total, down = false }: Props) {
  const path = usePathname();
  const [filter, setFilter] = useState<Filter>("all");
  const [model, setModel] = useState<string | null>(null);
  const [sort, setSort] = useState<SortId>("model");
  const models = modelsIn(games);
  // strongest models first unless another sort is chosen, and a model can be picked to see only its games
  const shown = sortGames(games, sort).filter(
    (g) => (filter === "all" || g.winner === filter) && (model === null || g.model === model),
  );
  const on = (match: string) => path === match || path.startsWith(`${match}/`);

  return (
    <aside className={styles.list} aria-label="Chats">
      <header className={styles.top}>
        <Link href="/" className={styles.brand} aria-label="Werewolf Coach, home">
          <span className={styles.marks} aria-hidden="true">
            <TeamMark team="Wolves" />
            <TeamMark team="Village" />
          </span>
          Werewolf Coach
        </Link>
        <p>Every player here is an AI agent.</p>
      </header>

      <nav aria-label="Chats">
        {down ? (
          <Waker>
            These {games.length} hand-picked games are saved in the site, so you can read them while you wait. The
            full list appears by itself.
          </Waker>
        ) : null}
        <ul className={styles.rows}>
          {PINNED.map((chat) => (
            <li key={chat.href}>
              <Link
                href={chat.href}
                className={styles.row}
                aria-current={on(chat.match) || (chat.match === "/welcome" && path === "/") ? "page" : undefined}
              >
                <ChatAvatar kind={chat.kind} />
                <span className={styles.text}>
                  <b>{chat.title}</b>
                  <span>{chat.line}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>

        <div className={styles.filters}>
          <div role="group" aria-label="Sort games">
            <span>Sort</span>
            {SORTS.map((s) => (
              <button key={s.id} type="button" aria-pressed={sort === s.id} onClick={() => setSort(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
          {models.length > 1 ? (
            <div role="group" aria-label="Filter by model">
              <span>Model</span>
              <button type="button" aria-pressed={model === null} onClick={() => setModel(null)}>
                All models
              </button>
              {models.map((m) => (
                <button key={m.model} type="button" aria-pressed={model === m.model} onClick={() => setModel(m.model)}>
                  {modelLabel(m.model)} <small>{m.games}</small>
                </button>
              ))}
            </div>
          ) : null}
          <div role="group" aria-label="Filter by winner">
            <span>Winner</span>
            {FILTERS.map((f) => (
              <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {shown.length === 0 ? (
          <p className={styles.empty}>No saved games match.</p>
        ) : (
          <ul className={styles.rows}>
            {shown.map((game) => (
              <li key={game.id}>
                <Link
                  href={`/games/${game.id}`}
                  className={styles.row}
                  aria-current={on(`/games/${game.id}`) ? "page" : undefined}
                >
                  <ChatAvatar kind={game.winner} />
                  <span className={styles.text}>
                    <b>Game {game.id}</b>
                    <span>
                      <TeamMark team={game.winner} word /> won in {plural(game.rounds, "round")}. {modelLabel(game.model)}
                    </span>
                  </span>
                  <small className={styles.note}>{game.rule_version}</small>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {games.length < total && !down ? (
          <p className={styles.empty}>
            Showing the latest {games.length} of {total} games.
          </p>
        ) : null}
      </nav>
    </aside>
  );
}
