"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { GameSummary } from "@/lib/api";
import { matchupOf, plural } from "@/lib/format";
import { ChatAvatar } from "./ChatAvatar";
import { TeamMark } from "./TeamMark";
import styles from "./ChatList.module.css";

type Props = {
  games: GameSummary[];
  total: number;
  /** The API did not answer, so the list of games is empty for that reason, not for lack of games. */
  down?: boolean;
};

const PINNED = [
  { href: "/welcome", match: "/welcome", kind: "welcome", title: "Werewolf Coach", line: "Start here: what this is" },
  { href: "/board", match: "/board", kind: "strategies", title: "Strategies", line: "The strategy cards and how each did" },
  { href: "/coach/wolf", match: "/coach", kind: "coach", title: "Coach", line: "The AI that rewrites the strategies" },
  { href: "/play", match: "/play", kind: "play", title: "Play", line: "Take a seat at the table", note: "soon" },
] as const;

type Filter = "all" | "Wolves" | "Village";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "Wolves", label: "Wolves won" },
  { id: "Village", label: "Village won" },
];

/** The list of chats on the left: the pinned ones, then every saved game, newest first. */
export function ChatList({ games, total, down = false }: Props) {
  const path = usePathname();
  const [filter, setFilter] = useState<Filter>("all");
  const shown = filter === "all" ? games : games.filter((g) => g.winner === filter);
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
                {"note" in chat ? <small className={styles.note}>{chat.note}</small> : null}
              </Link>
            </li>
          ))}
        </ul>

        <div className={styles.filters} role="group" aria-label="Filter the games">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>

        {down ? (
          <p className={styles.empty}>The games could not be loaded. The API may be starting up.</p>
        ) : shown.length === 0 ? (
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
                    <b>seed-{game.id}</b>
                    <span>
                      <TeamMark team={game.winner} word /> won in {plural(game.rounds, "round")}. {matchupOf(game.cards)}
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
