import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { IntervalBar } from "@/components/IntervalBar";
import { Revision } from "@/components/Revision";
import { api, apiOrNull } from "@/lib/api";
import type { Card, CoachHistory, Generation } from "@/lib/api";
import { ENOUGH_GAMES, cardParts, plural, sentence } from "@/lib/format";
import styles from "./coach.module.css";

type Props = { params: Promise<{ side: string }> };

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Coach" };

const SIDES = [
  { id: "wolf", label: "Wolves" },
  { id: "villager", label: "Villagers" },
] as const;

function spent(gen: Generation): number {
  const arms = [gen.champion_arm, gen.challenger_arm];
  return Number(gen.coach_cost) + arms.reduce((sum, arm) => sum + Number(arm?.cost ?? 0), 0);
}

export default async function CoachPage({ params }: Props) {
  const { side } = await params;
  const history = await apiOrNull<CoachHistory>(`/coach/${side}`);
  if (!history) notFound();
  const cards = new Map((await api<Card[]>("/strategies")).map((c) => [`${c.id}@${c.version}`, c]));
  const { generations } = history;
  const promoted = generations.filter((g) => g.promote).length;
  const start = generations[0]?.champion_before;
  const startCard = start ? cards.get(start) : undefined;

  return (
    <section className={styles.sheet} aria-labelledby="coach">
      <header className={styles.head}>
        <h1 id="coach">The coach</h1>
        <nav className={styles.sides} aria-label="Which side">
          {SIDES.map((s) => (
            <Link
              key={s.id}
              href={`/coach/${s.id}`}
              aria-current={s.id === side ? "true" : undefined}
            >
              {s.label}
            </Link>
          ))}
        </nav>
        {generations.length === 0 ? (
          <p>
            The coach has not run for this side yet. Start it from the command line with coach run.
          </p>
        ) : (
          <>
            <p className={styles.stamp}>
              {promoted === 0
                ? "None of the coach's cards beat the champion."
                : `${plural(promoted, "card")} beat the champion.`}
            </p>
            <p>
              {plural(generations.length, "generation")} so far. A new card replaces the champion
              only when it wins at least 30 points more often on the same seeds.
            </p>
          </>
        )}
      </header>

      {startCard ? (
        <div className={styles.pair}>
          <div className={styles.facing}>
            <h2>Where it started</h2>
            <p className={styles.sub}>
              The champion card, {cardParts(startCard.id).name}, version {startCard.version}. Source:{" "}
              {startCard.source}
            </p>
          </div>
          <div className={styles.script}>
            <p>{startCard.instructions}</p>
          </div>
        </div>
      ) : null}

      {generations.map((gen) => {
        const base = cards.get(gen.champion_before)?.instructions ?? null;
        return (
          <div
            key={gen.number}
            className={styles.pair}
            role="group"
            aria-labelledby={`g${gen.number}`}
          >
            <div className={styles.facing}>
              <h2 id={`g${gen.number}`}>Generation {gen.number}</h2>
              <p className={styles.sub}>
                Read {gen.evidence}. Cost ${spent(gen).toFixed(2)}.
              </p>
              <h3>What the coach concluded</h3>
              <p className={styles.notes}>{gen.diagnosis}</p>
            </div>

            <div className={styles.script}>
              {gen.challenger_card ? (
                <>
                  <h3>The new card, {cardParts(gen.challenger_card).name}</h3>
                  {gen.changes && gen.changes.length > 0 ? (
                    <Revision base={base} changes={gen.changes} />
                  ) : (
                    <>
                      <p>{gen.challenger_text}</p>
                      <p className={styles.sub}>
                        This generation was saved before edits were recorded, so the card is shown
                        as written, without cuts and additions marked.
                      </p>
                    </>
                  )}
                  <p className={styles.sub}>
                    Written in {plural(gen.check.attempts, "attempt")}, then checked for hidden
                    knowledge and broken rules before it played.
                  </p>
                </>
              ) : (
                <p className={styles.sub}>
                  {sentence(gen.decision)}. The coach wrote {plural(gen.check.attempts, "card")} and
                  none passed the checks, so no games were played.
                </p>
              )}

              {gen.champion_arm && gen.challenger_arm ? (
                <>
                  <h3>The test</h3>
                  <ul className={styles.arms}>
                    {[gen.champion_arm, gen.challenger_arm].map((arm, i) => (
                      <li key={arm.card}>
                        <span>{i === 0 ? "Champion" : "Challenger"}</span>
                        <b>{cardParts(arm.card).name}</b>
                        <IntervalBar
                          wins={arm.wins}
                          games={arm.games}
                          enough={arm.games >= ENOUGH_GAMES}
                          of="Won"
                        />
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}

              <p className={styles.verdict}>
                {gen.promote ? "New champion. " : "Champion stays. "}
                {sentence(gen.decision)}.
              </p>
            </div>
          </div>
        );
      })}
    </section>
  );
}
