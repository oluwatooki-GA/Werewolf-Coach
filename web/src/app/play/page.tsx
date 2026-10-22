import type { Metadata } from "next";
import { api } from "@/lib/api";
import type { PlayStatus } from "@/lib/api";
import styles from "../notice.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Play" };

export default async function PlayPage() {
  const status = await api<PlayStatus>("/play/status");
  return (
    <section className={styles.sheet} aria-labelledby="play">
      <h1 id="play">Play</h1>
      {status.available ? (
        <p>Play mode is open.</p>
      ) : (
        <>
          <p>
            Play mode is not built yet. When it is, you will take one seat at the table against
            seven AI players, with a turn timer, and the finished game will open as a replay with
            everyone&apos;s private notes.
          </p>
          <p className={styles.dim}>The server says: {status.reason}.</p>
        </>
      )}
    </section>
  );
}
