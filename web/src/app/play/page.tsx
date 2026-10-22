import type { Metadata } from "next";
import { ChannelHeader } from "@/components/ChannelHeader";
import { api } from "@/lib/api";
import type { PlayStatus } from "@/lib/api";
import styles from "../notice.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Play" };

export default async function PlayPage() {
  const status = await api<PlayStatus>("/play/status");
  return (
    <>
      <ChannelHeader name="play" topic="Take a seat at the table against seven AI players." />
      <div className={styles.page}>
        {status.available ? (
          <p>Play mode is open.</p>
        ) : (
          <>
            <p>
              Play mode is not built yet. When it is, you will join a game as one of the eight
              players, with a turn timer, and the finished game will open here as a chat with
              everyone&apos;s private notes.
            </p>
            <p className={styles.dim}>The server says: {status.reason}.</p>
          </>
        )}
      </div>
    </>
  );
}
