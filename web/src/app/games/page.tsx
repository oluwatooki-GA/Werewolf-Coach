import type { Metadata } from "next";
import { ChatAvatar } from "@/components/ChatAvatar";
import { api } from "@/lib/api";
import type { GameList } from "@/lib/api";
import { plural } from "@/lib/format";
import styles from "../notice.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Games" };

/** On a laptop the list is already on the left, so this is the empty chat window beside it. */
export default async function GamesPage() {
  const list = await api<GameList>("/games?limit=1&players=ai").catch(() => null); // asleep: say it without a count
  return (
    <div className={styles.idle}>
      <ChatAvatar kind="welcome" size={72} />
      <h1>Pick a game</h1>
      <p>
        {list ? `${plural(list.total, "game")} played by AI agents are saved. ` : ""}Open one from the list to watch
        it play like a live chat.
      </p>
    </div>
  );
}
