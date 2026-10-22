import Link from "next/link";
import { Room } from "@/components/Room";
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
      <section className={styles.intro} aria-labelledby="title">
        <h1 id="title">
          {replay && featured
            ? momentHeadline(replay.entries, featured.focus)
            : "Eight AI agents play Werewolf."}
        </h1>
        <p>
          Eight AI agents play Werewolf in a group chat. Click a message to read what its player
          privately thought when it sent it.
        </p>
        {replay && featured ? (
          <Link href={`/games/${replay.id}#${featured.focus}`} className={styles.read}>
            Read the whole game
          </Link>
        ) : null}
      </section>

      {replay && moment && featured ? (
        <>
          <Room
            entries={moment}
            players={replay.players}
            compact
            startAt={featured.focus}
            label="An excerpt of one game"
          />
          <p className={styles.provenance}>
            Seed {replay.seed}, played by {replay.model || "scripted agents"} under the{" "}
            {replay.rule_version} rules. The {replay.winner === "Wolves" ? "wolves" : "village"} won
            in {plural(replay.rounds, "round")}.
          </p>
        </>
      ) : (
        <p className={styles.provenance}>
          No game with a lie and a private note is stored yet. Seed the database with{" "}
          <code>app seed</code> and reload.
        </p>
      )}

      <ul className={styles.contents}>
        <Entry href="/games" title="replays">
          {games.total} saved games, each one a chat you can read with every private note.
        </Entry>
        <Entry href="/board" title="strategies">
          {plural(cards.length, "strategy card")} and how each one did, with the odds that a gap is
          real.
        </Entry>
        <Entry href="/coach/wolf" title="coach">
          {wolf.generations.length === 0
            ? "The coach has not run for the wolves yet."
            : `${plural(wolf.generations.length, "generation")} on the wolf side. ${
                promoted === 0 ? "None beat the champion." : `${promoted} beat the champion.`
              }`}
        </Entry>
        <Entry href="/play" title="play">
          Take a seat against the agents. Not built yet.
        </Entry>
      </ul>
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
