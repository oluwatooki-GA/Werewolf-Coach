import type { ReplayLine, ReplayPlayer, ReplayVote } from "@/lib/api";
import { markName, moveName, percent, plural, sentence } from "@/lib/format";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import { TeamMark } from "./TeamMark";
import styles from "./Thoughts.module.css";

type Props = {
  entry: ReplayLine | ReplayVote | null;
  cast: Map<string, ReplayPlayer>;
  showRoles: boolean;
  /** Where it is shown: the info column on a laptop, or inline under the bubble in the welcome chat. */
  surface: "panel" | "inline";
};

/** What the player privately wrote when it sent the selected message, and what the lab found. */
export function Thoughts({ entry, cast, showRoles, surface }: Props) {
  if (!showRoles) {
    return (
      <section className={styles.box} data-surface={surface} aria-label="Private thoughts">
        <p className={styles.hint}>
          Roles and private notes are hidden. Turn them on in the chat options (⋮) to read what each player was
          thinking.
        </p>
      </section>
    );
  }
  if (!entry) {
    return (
      <section className={styles.box} data-surface={surface} aria-label="Private thoughts">
        <h3>Private thoughts</h3>
        <p className={styles.hint}>Tap a message to read what its player was thinking when they sent it.</p>
      </section>
    );
  }
  const name = entry.kind === "line" ? entry.speaker : entry.voter;
  const { subtext, marks } = entry;
  const plan = subtext
    ? [
        subtext.bid !== null && subtext.bid !== undefined ? `Bid ${plural(subtext.bid, "token")} to speak next.` : null,
        subtext.intent
          ? `Plan: ${moveName(subtext.intent)}${subtext.target ? `, aimed at ${subtext.target}` : ""}.`
          : subtext.target
            ? `Aimed at ${subtext.target}.`
            : null,
      ].filter(Boolean)
    : [];
  const beliefs = [...(subtext?.beliefs ?? [])].sort((a, b) => b.suspicion - a.suspicion).slice(0, 5);

  return (
    <section className={styles.box} data-surface={surface} aria-label={`Private thoughts of ${name}`}>
      <header className={styles.head}>
        <Avatar name={name} size={36} />
        <div>
          <b>{name}</b> <RoleTag role={entry.role} team={entry.team} />
          <p>{entry.kind === "line" ? "Before sending this message" : "Before voting"}</p>
        </div>
      </header>

      {entry.kind === "vote" && entry.reason ? (
        <>
          <h4>What {name} said</h4>
          <p className={styles.said}>
            Voted for {entry.target ?? "nobody"}: {entry.reason}
          </p>
        </>
      ) : null}

      <h4>{name}&apos;s private note</h4>
      {subtext?.note ? (
        <blockquote className={styles.note}>{subtext.note}</blockquote>
      ) : (
        <p className={styles.hint}>No private note was recorded for this message.</p>
      )}

      {plan.length > 0 ? <p className={styles.cue}>{plan.join(" ")}</p> : null}

      {beliefs.length > 0 && entry.role === "Werewolf" ? (
        <details className={styles.wolfTable}>
          <summary>{name} is a wolf, so this is not a real suspicion list</summary>
          <p className={styles.explain}>
            Wolves already know who the wolves are. The game asks every player for the same table, so {name} filled it
            in anyway. Treat the numbers as talk, not as what {name} believed.
          </p>
          <ul className={styles.beliefs}>
            {beliefs.map((belief) => (
              <li key={belief.player}>
                <span className={styles.who}>{belief.player}</span>
                <svg viewBox="0 0 80 8" width="80" height="8" aria-hidden="true">
                  <rect width="80" height="8" rx="4" className={styles.track} />
                  <rect width={80 * belief.suspicion} height="8" rx="4" className={styles.fill} />
                </svg>
                <span className={styles.pct}>{percent(belief.suspicion)}</span>
                {belief.reason ? <small>{belief.reason}</small> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {beliefs.length > 0 && entry.role !== "Werewolf" ? (
        <>
          <h4>Who {name} thought was a wolf</h4>
          <p className={styles.explain}>The longer the bar, the more sure {name} was.</p>
          <ul className={styles.beliefs}>
            {beliefs.map((belief) => {
              const them = cast.get(belief.player);
              return (
                <li key={belief.player}>
                  <span className={styles.who}>
                    {belief.player}
                    {them ? <TeamMark team={them.team} /> : null}
                  </span>
                  <svg viewBox="0 0 80 8" width="80" height="8" aria-hidden="true">
                    <rect width="80" height="8" rx="4" className={styles.track} />
                    <rect width={80 * belief.suspicion} height="8" rx="4" className={styles.fill} />
                  </svg>
                  <span className={styles.pct}>{percent(belief.suspicion)}</span>
                  {belief.reason ? <small>{belief.reason}</small> : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}

      {marks.length > 0 ? (
        <>
          <h4>Checked against the real roles</h4>
          <ul className={styles.findings}>
            {marks.map((mark) => (
              <li key={mark.label} data-flag={mark.label === "lie" ? "lie" : undefined}>
                <b>{markName(mark.label)}</b> {sentence(mark.why)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
