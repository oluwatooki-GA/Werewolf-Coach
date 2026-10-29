"use client";

import { useEffect, useState } from "react";
import type { Generation } from "@/lib/api";
import { ENOUGH_GAMES, cardParts, plural, sentence } from "@/lib/format";
import { IntervalBar } from "./IntervalBar";
import { Embed, Post } from "./Post";
import { Revision } from "./Revision";
import { Typing } from "./Typing";
import styles from "./CoachThoughts.module.css";

function spent(gen: Generation): number {
  const arms = [gen.champion_arm, gen.challenger_arm];
  return Number(gen.coach_cost) + arms.reduce((sum, arm) => sum + Number(arm?.cost ?? 0), 0);
}

/**
 * What the coach thought in one generation, said as chat: what it read, what it concluded, what
 * it changed, how the test went. The messages arrive one at a time with "typing", like the games
 * do, and all at once for a reader who asks for less motion.
 */
export function CoachThoughts({ gen, base }: { gen: Generation; base: string | null }) {
  const arms = gen.champion_arm && gen.challenger_arm ? [gen.champion_arm, gen.challenger_arm] : null;
  const messages: React.ReactNode[] = [
    <p key="read">
      I read {gen.evidence}.{gen.champion_arm ? ` Each card then played ${plural(gen.champion_arm.games, "game")}.` : ""}{" "}
      The run cost ${spent(gen).toFixed(2)}.
    </p>,
    <Embed key="concluded" title="What I concluded">
      <p className={styles.concluded}>{gen.diagnosis}</p>
    </Embed>,
    gen.challenger_card ? (
      <div key="changed" className={styles.stack}>
        <p>
          The new card is {cardParts(gen.challenger_card).name}. It took {plural(gen.check.attempts, "attempt")} and was
          checked for hidden knowledge and broken rules before it played.
        </p>
        <Embed title="What I changed">
          {gen.changes && gen.changes.length > 0 ? (
            <Revision base={base} changes={gen.changes} />
          ) : (
            <>
              <p>{gen.challenger_text}</p>
              <p className={styles.note}>
                This generation was saved before edits were recorded, so the card is shown as written, without cuts and
                additions marked.
              </p>
            </>
          )}
        </Embed>
      </div>
    ) : (
      <p key="none">
        {sentence(gen.decision)}. I wrote {plural(gen.check.attempts, "card")} and none passed the checks, so no games
        were played.
      </p>
    ),
    ...(arms
      ? [
          <div key="result" className={styles.stack}>
            <p>Test results, both cards on the same seeds:</p>
            <Embed>
              <ul className={styles.arms}>
                {arms.map((arm, i) => (
                  <li key={arm.card}>
                    <span>{i === 0 ? "Champion" : "Challenger"}</span>
                    <b>{cardParts(arm.card).name}</b>
                    <IntervalBar wins={arm.wins} games={arm.games} enough={arm.games >= ENOUGH_GAMES} of="Won" />
                  </li>
                ))}
              </ul>
            </Embed>
            <p>
              <b>{gen.promote ? "New champion." : "Champion stays."}</b> {sentence(gen.decision)}.
            </p>
          </div>,
        ]
      : []),
  ];

  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reads the browser once, after hydration
      setShown(messages.length);
      return;
    }
    if (shown >= messages.length) return;
    const timer = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 900 : 1300);
    return () => window.clearTimeout(timer);
  }, [shown, messages.length]);

  const typing = shown < messages.length;
  return (
    <section className={styles.thoughts} aria-label="The coach's thoughts">
      <h4>
        The coach&apos;s thoughts{typing ? <em> Coach is typing…</em> : null}
      </h4>
      <div className={styles.chat}>
        {messages.slice(0, shown).map((message, i) => (
          <Post key={i} name="Coach" bot first={i === 0}>
            {message}
          </Post>
        ))}
        {typing ? <Typing name="Coach" /> : null}
      </div>
    </section>
  );
}
