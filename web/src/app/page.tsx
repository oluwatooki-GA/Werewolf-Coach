import Link from "next/link";
import { Room } from "@/components/Room";
import { api, apiOrNull } from "@/lib/api";
import type { Card, CoachHistory, Featured, GameList, Replay } from "@/lib/api";
import { plural } from "@/lib/format";
import { excerpt } from "@/lib/replay";
import styles from "./home.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export default async function Home() {
  const [featured, games, cards, wolf] = await Promise.all([
    apiOrNull<Featured>("/featured"),
    api<GameList>("/games?limit=1"),
    api<Card[]>("/strategies"),
    api<CoachHistory>("/coach/wolf"),
  ]);
  const replay = featured ? await apiOrNull<Replay>(`/games/${featured.game_id}/replay`) : null;
  const moment = replay && featured ? excerpt(replay.entries, featured.focus) : null;
  const promoted = wolf.generations.filter((g) => g.promote).length;

  return (
    <>
      <section className={styles.intro} aria-labelledby="title">
        <h1 id="title">Eight AI agents play Werewolf. Some of them lie.</h1>
        <p>
          Werewolf is a chat game. Two players are secretly wolves, the other six are villagers, and
          everyone talks and votes someone out each day. Here you can watch AI agents play it, and
          read what each one was privately thinking.
        </p>
      </section>

      {replay && moment && featured ? (
        <section className={styles.demo} aria-label="A short demo">
          <Room
            entries={moment}
            players={replay.players}
            compact
            story
            startAt={featured.focus}
            label="A moment from one game"
          />
          <p className={styles.after}>
            <Link href={`/games/${replay.id}`} className={styles.read}>
              Watch the whole game
            </Link>
            <span>
              Seed {replay.seed}, played by {replay.model || "scripted agents"}. The{" "}
              {replay.winner === "Wolves" ? "wolves" : "village"} won in{" "}
              {plural(replay.rounds, "round")}.
            </span>
          </p>
        </section>
      ) : (
        <p className={styles.empty}>
          No game with a lie and a private note is stored yet. Seed the database with{" "}
          <code>app seed</code> and reload.
        </p>
      )}

      <section className={styles.more} aria-labelledby="more">
        <h2 id="more">Keep going</h2>
        <ul>
          <Entry href="/games" title="replays">
            {games.total} saved games. Each plays back like a live chat, with every private note.
          </Entry>
          <Entry href="/board" title="strategies">
            {plural(cards.length, "strategy card")} that tell an agent how to play, and how each one
            did.
          </Entry>
          <Entry href="/coach/wolf" title="coach">
            {wolf.generations.length === 0
              ? "An AI coach that rewrites the wolves' strategy. It has not run yet."
              : `An AI coach that rewrites the wolves' strategy. ${plural(wolf.generations.length, "try")} so far, ${
                  promoted === 0 ? "none better than the current champion" : `${promoted} better than the champion`
                }.`}
          </Entry>
          <Entry href="/play" title="play">
            Take a seat against the agents. Not built yet.
          </Entry>
        </ul>
      </section>
    </>
  );
}

function Entry({
  href,
  title,
  children,
}: {
  href: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li>
      <Link href={href}>
        <b>
          <span aria-hidden="true">#</span> {title}
        </b>
        <span>{children}</span>
      </Link>
    </li>
  );
}
