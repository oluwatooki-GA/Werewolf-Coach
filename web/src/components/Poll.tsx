import type { ReplayVote } from "@/lib/api";
import { plural } from "@/lib/format";
import { Avatar } from "./Avatar";
import { TeamMark } from "./TeamMark";
import messages from "./Message.module.css";
import styles from "./Poll.module.css";

export type Ballot = { id: string; vote: ReplayVote };

type Props = {
  round: number;
  /** The votes cast so far, in the order they came in. */
  ballots: Ballot[];
  /** How many votes this round will have in the end, so the bars know their scale. */
  expected: number;
  selected: string | null;
  isolated: string | null;
  showRoles: boolean;
  /** The newest ballot, which slides in while the game plays. */
  fresh: string | null;
  onSelect: (id: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void;
};

/**
 * A day's vote as a poll, like WhatsApp's: one option per player voted for, a bar, a count, and
 * under it who voted that way. Tapping a voter opens why they voted, and what they thought.
 */
export function Poll({ round, ballots, expected, selected, isolated, showRoles, fresh, onSelect, onKeyDown }: Props) {
  const options = new Map<string, Ballot[]>();
  for (const ballot of ballots) {
    const key = ballot.vote.target ?? "";
    options.set(key, [...(options.get(key) ?? []), ballot]);
  }
  const done = ballots.length >= expected;
  const top = Math.max(0, ...[...options.values()].map((v) => v.length));
  const tied = [...options.values()].filter((v) => v.length === top).length > 1;
  // while votes come in the options keep the order they appeared in; a finished poll ranks them
  const ranked = done ? [...options].sort((a, b) => b[1].length - a[1].length) : [...options];

  return (
    <div className={messages.row} data-side="in" data-static>
      <span className={messages.gutter} />
      <section className={`${messages.bubble} ${styles.poll}`} aria-label={`Vote, round ${round}`}>
        <header className={styles.head}>
          <b>Who should be voted out?</b>
          <small>
            Round {round} vote. {done ? plural(expected, "vote") : `${ballots.length} of ${expected} votes in`}. Tap a name to
            see why.
          </small>
        </header>
        <ul className={styles.options}>
          {ranked.map(([target, votes]) => {
            const leads = done && votes.length === top;
            return (
              <li key={target || "none"} data-leads={leads || undefined}>
                <div className={styles.line}>
                  <span className={styles.check} aria-hidden="true" data-on={leads || undefined}>
                    {leads ? (
                      <svg viewBox="0 0 12 12" width="12" height="12" focusable="false">
                        <path d="m2.5 6.2 2.3 2.3 4.7-5" fill="none" stroke="currentColor" strokeWidth="1.8" />
                      </svg>
                    ) : null}
                  </span>
                  <span className={styles.name}>{target || "No vote"}</span>
                  {leads ? <em>{tied ? "Tied" : "Most votes"}</em> : null}
                  <span className={styles.count}>{votes.length}</span>
                </div>
                <div className={styles.bar} aria-hidden="true">
                  <i style={{ width: `${(votes.length / Math.max(expected, 1)) * 100}%` }} />
                </div>
                <ul className={styles.voters}>
                  {votes.map(({ id, vote }) => (
                    <li key={id}>
                      <button
                        type="button"
                        id={id}
                        data-msg
                        data-id={id}
                        className={styles.voter}
                        aria-current={selected === id ? "true" : undefined}
                        data-fresh={fresh === id || undefined}
                        data-dim={isolated !== null && isolated !== vote.voter ? "" : undefined}
                        aria-label={`${vote.voter} voted for ${vote.target ?? "nobody"}. Tap to see why.`}
                        onClick={() => onSelect(id)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape" || event.key === "ArrowDown" || event.key === "ArrowUp") onKeyDown(event);
                        }}
                      >
                        <Avatar name={vote.voter} size={20} />
                        {vote.voter}
                        {showRoles && vote.team === "Wolves" ? <TeamMark team="Wolves" /> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
