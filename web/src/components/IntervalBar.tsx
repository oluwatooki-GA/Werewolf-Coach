import { percent, wilson } from "@/lib/format";
import styles from "./IntervalBar.module.css";

type Props = {
  wins: number;
  games: number;
  /** Fewer games than this and the bar is dashed and called "not clear yet". */
  enough: boolean;
  /** Spell out what a win means, for screen readers: "wolves won". */
  of: string;
};

const W = 200;
const PAD = 6;
const at = (rate: number) => PAD + rate * (W - 2 * PAD);

/**
 * A win rate drawn with its uncertainty: a dot at the observed rate on a 0 to 100% line, and a
 * bar over the 95% interval. Thin data is dashed, never solid, and says so in words.
 */
export function IntervalBar({ wins, games, enough, of }: Props) {
  const [low, high] = wilson(wins, games);
  const rate = games === 0 ? 0 : wins / games;
  const summary =
    `${of} in ${wins} of ${games} games, ${percent(rate)}. ` +
    `The 95% interval runs from ${percent(low)} to ${percent(high)}.` +
    (enough ? "" : " Not clear yet.");
  return (
    <figure className={styles.figure}>
      <svg
        viewBox={`0 0 ${W} 22`}
        className={styles.svg}
        role="img"
        aria-label={summary}
        focusable="false"
      >
        <line x1={at(0)} x2={at(1)} y1="11" y2="11" className={styles.axis} />
        <line x1={at(0.5)} x2={at(0.5)} y1="5" y2="17" className={styles.half} />
        <line
          x1={at(low)}
          x2={at(high)}
          y1="11"
          y2="11"
          className={enough ? styles.interval : styles.thin}
        />
        <circle cx={at(rate)} cy="11" r="4.5" className={styles.dot} />
      </svg>
      <figcaption>
        <b>{percent(rate)}</b> <span>{wins}/{games}</span>
        {enough ? null : <em>not clear yet</em>}
      </figcaption>
    </figure>
  );
}
