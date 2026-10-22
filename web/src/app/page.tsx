import Link from "next/link";
import { Spread } from "@/components/Spread";
import { api, apiOrNull } from "@/lib/api";
import type { Card, CoachHistory, Featured, GameList, Replay } from "@/lib/api";
import { plural } from "@/lib/format";
import { excerpt, momentHeadline } from "@/lib/replay";
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
      <div className={styles.book}>
        <section className={styles.title} aria-labelledby="title">
          <h1 id="title">
            {replay && featured
              ? momentHeadline(replay.entries, featured.focus)
              : "Eight AI agents play Werewolf."}
          </h1>
          <p>
            Eight AI agents play Werewolf. On the right is what a player said out loud. On the left
            is what it privately wrote at that moment.
          </p>
          {replay && featured ? (
            <Link href={`/games/${replay.id}#${featured.focus}`} className={styles.read}>
              Read the whole game
            </Link>
          ) : null}
        </section>

        {replay && moment && featured ? (
          <Spread
            entries={moment}
            players={replay.players}
            showNotes
            acts={false}
            flat
            startAt={featured.focus}
            label="An excerpt of one game: public lines beside private notes"
          />
        ) : (
          <p className={styles.empty}>
            No game with a lie and a private note is stored yet. Seed the database with{" "}
            <code>app seed</code> and reload.
          </p>
        )}
      </div>

      {replay && featured ? (
        <div className={`on-house ${styles.provenance}`}>
          <p>
            Seed {replay.seed}, played by {replay.model || "scripted agents"} under the{" "}
            {replay.rule_version} rules. The {replay.winner === "Wolves" ? "wolves" : "village"} won
            in {plural(replay.rounds, "round")}.
          </p>
          <Link href="/games" className={styles.action}>
            More games
          </Link>
        </div>
      ) : null}

      <dl className={`on-house ${styles.contents}`}>
        <Entry href="/games" gel={1} title="Replays">
          {games.total} saved games. Each one opens as a script with the private notes beside it.
        </Entry>
        <Entry href="/board" gel={0} title="Strategies">
          {plural(cards.length, "strategy card")} and how each one did, with the odds that a gap is
          real.
        </Entry>
        <Entry href="/coach/wolf" gel={3} title="Coach">
          {wolf.generations.length === 0
            ? "The coach has not run for the wolves yet."
            : `${plural(wolf.generations.length, "generation")} on the wolf side. ${
                promoted === 0 ? "None beat the champion." : `${promoted} beat the champion.`
              }`}
        </Entry>
        <Entry href="/play" gel={5} title="Play">
          Take a seat against the agents. Not built yet.
        </Entry>
      </dl>
    </>
  );
}

function Entry({
  href,
  gel,
  title,
  children,
}: {
  href: string;
  gel: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.entry} style={{ ["--gel" as string]: `var(--gel-${gel})` }}>
      <dt>
        <Link href={href}>{title}</Link>
      </dt>
      <dd>{children}</dd>
    </div>
  );
}
