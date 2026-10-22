import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChannelHeader } from "@/components/ChannelHeader";
import { IntervalBar } from "@/components/IntervalBar";
import { Embed, Post } from "@/components/Post";
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
  { id: "wolf", label: "wolves" },
  { id: "villager", label: "villagers" },
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
  const label = SIDES.find((s) => s.id === side)?.label ?? side;

  return (
    <>
      <ChannelHeader
        name={`coach-${label}`}
        topic="The coach reads the games a side lost, writes a challenger card, and tests it on the same seeds as the champion."
      >
        <nav className={styles.sides} aria-label="Which side">
          {SIDES.map((s) => (
            <Link
              key={s.id}
              href={`/coach/${s.id}`}
              className={styles.pill}
              aria-current={s.id === side ? "true" : undefined}
            >
              {s.label}
            </Link>
          ))}
        </nav>
      </ChannelHeader>

      <div className={styles.thread}>
        {generations.length === 0 ? (
          <p className={styles.empty}>
            The coach has not run for this side yet. Start it from the command line with coach run.
          </p>
        ) : (
          <p className={styles.pinned} role="note">
            <b>
              {promoted === 0
                ? "None of the coach's cards beat the champion."
                : `${plural(promoted, "card")} beat the champion.`}
            </b>{" "}
            {plural(generations.length, "generation")} so far. A new card replaces the champion only
            when it wins at least 30 points more often on the same seeds.
          </p>
        )}

        {startCard ? (
          <Post name="Lab" bot>
            <p>
              The starting champion is {cardParts(startCard.id).name}, version {startCard.version}.
              Source: {startCard.source}
            </p>
            <Embed>
              <p>{startCard.instructions}</p>
            </Embed>
          </Post>
        ) : null}

        {generations.map((gen) => {
          const base = cards.get(gen.champion_before)?.instructions ?? null;
          return (
            <section key={gen.number} aria-labelledby={`g${gen.number}`}>
              <h2 className={styles.divider} id={`g${gen.number}`}>
                <span>Generation {gen.number}</span>
              </h2>

              <Post name="Coach" bot>
                <p>
                  I read {gen.evidence}.
                  {gen.champion_arm
                    ? ` Each card then played ${plural(gen.champion_arm.games, "game")}.`
                    : ""}{" "}
                  The run cost ${spent(gen).toFixed(2)}.
                </p>
                <Embed title="What I concluded">
                  <p className={styles.concluded}>{gen.diagnosis}</p>
                </Embed>
              </Post>

              {gen.challenger_card ? (
                <Post name="Coach" bot>
                  <p>
                    The new card is {cardParts(gen.challenger_card).name}. It took{" "}
                    {plural(gen.check.attempts, "attempt")} and was checked for hidden knowledge and
                    broken rules before it played.
                  </p>
                  <Embed title={cardParts(gen.challenger_card).name}>
                    {gen.changes && gen.changes.length > 0 ? (
                      <Revision base={base} changes={gen.changes} />
                    ) : (
                      <>
                        <p>{gen.challenger_text}</p>
                        <p className={styles.note}>
                          This generation was saved before edits were recorded, so the card is
                          shown as written, without cuts and additions marked.
                        </p>
                      </>
                    )}
                  </Embed>
                </Post>
              ) : (
                <Post name="Coach" bot>
                  <p>
                    {sentence(gen.decision)}. I wrote {plural(gen.check.attempts, "card")} and none
                    passed the checks, so no games were played.
                  </p>
                </Post>
              )}

              {gen.champion_arm && gen.challenger_arm ? (
                <Post name="Lab" bot>
                  <p>Test results, both cards on the same seeds:</p>
                  <Embed>
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
                  </Embed>
                </Post>
              ) : null}

              <p className={styles.verdict}>
                {gen.promote ? "New champion. " : "Champion stays. "}
                {sentence(gen.decision)}.
              </p>
            </section>
          );
        })}
      </div>
    </>
  );
}
