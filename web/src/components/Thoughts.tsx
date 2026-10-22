import type { ReplayLine, ReplayPlayer, ReplayVote } from "@/lib/api";
import { moveName } from "@/lib/format";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import { TeamMark } from "./TeamMark";
import styles from "./Thoughts.module.css";

type Props = {
  entry: ReplayLine | ReplayVote | null;
  cast: Map<string, ReplayPlayer>;
  showRoles: boolean;
  /** Where it is shown: the side panel on a laptop, or inline under the message on a phone. */
  surface: "panel" | "inline";
};

/** What the player privately wrote when it sent the selected message, and what the lab found. */
export function Thoughts({ entry, cast, showRoles, surface }: Props) {
  if (!showRoles) {
    return (
      <section className={styles.box} data-surface={surface} aria-label="Private thoughts">
        <p className={styles.hint}>Roles and private notes are hidden. Turn them on to read what each player was thinking.</p>
      </section>
    );
  }
  if (!entry) {
    return (
      <section className={styles.box} data-surface={surface} aria-label="Private thoughts">
        <h3>Private thoughts</h3>
        <p className={styles.hint}>Select a message to read what its player was thinking when it sent it.</p>
      </section>
    );
  }
  const name = entry.kind === "line" ? entry.speaker : entry.voter;
  const { subtext, marks } = entry;
  const cue = subtext
    ? [
        subtext.bid !== null && subtext.bid !== undefined ? `Bid ${subtext.bid}` : null,
        subtext.intent ? moveName(subtext.intent) : null,
        subtext.target ? `to ${subtext.target}` : null,
      ].filter(Boolean)
    : [];
  const beliefs = [...(subtext?.beliefs ?? [])].sort((a, b) => b.suspicion - a.suspicion).slice(0, 5);

  return (
    <section className={styles.box} data-surface={surface} aria-label={`Private thoughts of ${name}`}>
      <header className={styles.head}>
        <Avatar name={name} size={32} />
        <div>
          <b>{name}</b> <RoleTag role={entry.role} team={entry.team} />
          <p>{entry.kind === "line" ? `Thinking before ${entry.ref}` : "Thinking before voting"}</p>
        </div>
      </header>

      {subtext?.note ? (
        <blockquote className={styles.note}>{subtext.note}</blockquote>
      ) : (
        <p className={styles.hint}>No private note was recorded for this message.</p>
      )}

      {cue.length > 0 ? <p className={styles.cue}>{cue.join(", ")}</p> : null}

      {beliefs.length > 0 ? (
        <>
          <h4>Who {name} suspected</h4>
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
                  <span>{belief.suspicion.toFixed(1)}</span>
                  {belief.reason ? <small>{belief.reason}</small> : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}

      {marks.length > 0 ? (
        <>
          <h4>What the lab found</h4>
          <ul className={styles.findings}>
            {marks.map((mark) => (
              <li key={mark.label} data-flag={mark.label === "lie" ? "lie" : undefined}>
                <b>{moveName(mark.label)}</b> {mark.why}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
