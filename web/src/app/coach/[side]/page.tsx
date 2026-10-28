import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Chips } from "@/components/Chips";
import { IntervalBar } from "@/components/IntervalBar";
import { Pill } from "@/components/Pill";
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
  const label = SIDES.find((s) => s.id === side)?.label ?? side;

  return (
    <ChatPage
      avatar={<ChatAvatar kind="coach" size={40} />}
      title={`Coach: ${label.toLowerCase()}`}
      subtitle="Reads lost games, writes a new card, tests it on the same seeds"
      actions={
        <Chips
          label="Which side"
          items={SIDES.map((s) => ({ href: `/coach/${s.id}`, text: s.label, current: s.id === side }))}
        />
      }
    >
      {generations.length === 0 ? (
        <Pill as="div" tone="notice">
          <p>The coach has not run for this side yet. Start it from the command line with coach run.</p>
        </Pill>
      ) : (
        <Pill as="div" tone="notice">
          <p>
            <b>
              {promoted === 0
                ? "None of the coach's cards beat the champion."
                : `${plural(promoted, "card")} beat the champion.`}
            </b>
          </p>
          <p>
            {plural(generations.length, "generation")} so far. A new card replaces the champion only when it wins at
            least 30 points more often on the same seeds.
          </p>
        </Pill>
      )}

      {startCard ? (
        <Post name="Lab" bot>
          <p>
            The starting champion is {cardParts(startCard.id).name}, version {startCard.version}. Source:{" "}
            {startCard.source}
          </p>
          <Embed>
            <p>{startCard.instructions}</p>
          </Embed>
        </Post>
      ) : null}

      {generations.map((gen) => {
        const base = cards.get(gen.champion_before)?.instructions ?? null;
        return (
          <section key={gen.number} aria-labelledby={`g${gen.number}`} className={styles.generation}>
            <Pill as="h2" tone="date" id={`g${gen.number}`}>
              Generation {gen.number}
            </Pill>

            <Post name="Coach" bot>
              <p>
                I read {gen.evidence}.
                {gen.champion_arm ? ` Each card then played ${plural(gen.champion_arm.games, "game")}.` : ""} The run
                cost ${spent(gen).toFixed(2)}.
              </p>
              <Embed title="What I concluded">
                <p className={styles.concluded}>{gen.diagnosis}</p>
              </Embed>
            </Post>

            {gen.challenger_card ? (
              <Post name="Coach" bot first={false}>
                <p>
                  The new card is {cardParts(gen.challenger_card).name}. It took {plural(gen.check.attempts, "attempt")}{" "}
                  and was checked for hidden knowledge and broken rules before it played.
                </p>
                <Embed title={cardParts(gen.challenger_card).name}>
                  {gen.changes && gen.changes.length > 0 ? (
                    <Revision base={base} changes={gen.changes} />
                  ) : (
                    <>
                      <p>{gen.challenger_text}</p>
                      <p className={styles.note}>
                        This generation was saved before edits were recorded, so the card is shown as written, without
                        cuts and additions marked.
                      </p>
                    </>
                  )}
                </Embed>
              </Post>
            ) : (
              <Post name="Coach" bot first={false}>
                <p>
                  {sentence(gen.decision)}. I wrote {plural(gen.check.attempts, "card")} and none passed the checks, so
                  no games were played.
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

            <Pill tone="end">
              {gen.promote ? "New champion. " : "Champion stays. "}
              {sentence(gen.decision)}.
            </Pill>
          </section>
        );
      })}
    </ChatPage>
  );
}
