"use client";

import { usePathname } from "next/navigation";
import type { GameSummary } from "@/lib/api";
import { ChatList } from "./ChatList";
import styles from "./Shell.module.css";

type Props = { games: GameSummary[]; total: number; down: boolean; children: React.ReactNode };

/**
 * The messenger frame: the list of chats beside the open chat. On a phone only one shows at a
 * time: the list on the home page and the games list, the chat everywhere else.
 */
export function Shell({ games, total, down, children }: Props) {
  const path = usePathname();
  const screen = path === "/" || path === "/games" ? "list" : "chat";
  return (
    <div className={styles.shell} data-screen={screen}>
      <ChatList games={games} total={total} down={down} />
      <main id="main" className={styles.main}>
        {children}
      </main>
    </div>
  );
}
