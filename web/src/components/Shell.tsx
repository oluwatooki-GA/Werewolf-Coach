"use client";

import { usePathname } from "next/navigation";
import type { GameSummary } from "@/lib/api";
import { ChatList } from "./ChatList";
import { Splitter, useWidth } from "./Splitter";
import styles from "./Shell.module.css";

type Props = { games: GameSummary[]; total: number; down: boolean; children: React.ReactNode };

/**
 * The messenger frame: the list of chats beside the open chat. The reader can drag the edge
 * between them. On a phone only one shows at a time: the list on the home page and the games
 * list, the chat everywhere else.
 */
export function Shell({ games, total, down, children }: Props) {
  const path = usePathname();
  const screen = path === "/" || path === "/games" ? "list" : "chat";
  const [width, setWidth, resetWidth] = useWidth("werewolf-coach.list-width", 384, 224, 560);
  return (
    <div
      className={styles.shell}
      data-screen={screen}
      style={{ "--list-width": `${width}px` } as React.CSSProperties}
    >
      <ChatList games={games} total={total} down={down} />
      <Splitter
        label="Chat list width"
        grow="right"
        value={width}
        min={224}
        max={560}
        onChange={setWidth}
        onReset={resetWidth}
        className={styles.edge}
      />
      <main id="main" className={styles.main}>
        {children}
      </main>
    </div>
  );
}
