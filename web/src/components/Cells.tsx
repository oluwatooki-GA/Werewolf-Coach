import type { ReplayEntry, ReplayLine, ReplayPlayer, ReplayVote, Subtext } from "@/lib/api";
import { moveName, plural } from "@/lib/format";
import { TeamMark } from "./TeamMark";
import styles from "./Spread.module.css";

type Team = "Village" | "Wolves";

/** The role of a named player, so a belief can show whether it was right. */
export type Cast = Map<string, ReplayPlayer>;

function Beliefs({ subtext, cast }: { subtext: Subtext; cast: Cast }) {
  const top = [...subtext.beliefs].sort((a, b) => b.suspicion - a.suspicion).slice(0, 3);
  if (top.length === 0) return null;
  return (
    <ul className={styles.beliefs} aria-label="Who this player suspected">
      {top.map((belief) => {
        const them = cast.get(belief.player);
        return (
          <li key={belief.player}>
            <span>{belief.player}</span>
            {them ? <TeamMark team={them.team as Team} /> : null}
            <svg viewBox="0 0 48 6" width="48" height="6" aria-hidden="true" className={styles.bar}>
              <rect x="0.5" y="0.5" width="47" height="5" fill="none" stroke="currentColor" />
              <rect x="0.5" y="0.5" width={47 * belief.suspicion} height="5" fill="currentColor" />
            </svg>
            <span>{belief.suspicion.toFixed(1)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** What the speaker privately wrote beside a line, plus what the lab found out about it. */
export function SubtextCell({ line, cast }: { line: ReplayLine; cast: Cast }) {
  const { subtext, marks } = line;
  if (!subtext && marks.length === 0) return null;
  const cue = subtext
    ? [
        subtext.bid !== null && subtext.bid !== undefined ? `bid ${subtext.bid}` : null,
        subtext.intent ? moveName(subtext.intent) : null,
        subtext.target ? `to ${subtext.target}` : null,
      ].filter(Boolean)
    : [];
  return (
    <aside className={styles.subtext} aria-label={`Private notes for ${line.ref}`}>
      <p className={styles.speaker}>
        <TeamMark team={line.team as Team} />
        <span>
          {line.speaker}, {line.role}
        </span>
      </p>
      {subtext?.note ? <p className={styles.note}>{subtext.note}</p> : null}
      {cue.length > 0 ? <p className={styles.cuedata}>{cue.join(", ")}</p> : null}
      {subtext ? <Beliefs subtext={subtext} cast={cast} /> : null}
      {marks.map((mark) => (
        <p className={styles.finding} key={mark.label}>
          <span>{moveName(mark.label)}</span> {mark.why}
        </p>
      ))}
    </aside>
  );
}

function Cites({ line, known }: { line: ReplayLine; known: Set<string> }) {
  if (line.cites.length === 0) return null;
  return (
    <p className={styles.cites}>
      cites{" "}
      {line.cites.map((cite, index) => (
        <span key={cite.line}>
          {index > 0 ? ", " : ""}
          {known.has(cite.line) ? <a href={`#${cite.line}`}>{cite.line}</a> : cite.line}
          {line.invented.includes(cite.line) ? " (not a real line)" : ""}
        </span>
      ))}
    </p>
  );
}

/** One public line, set like a script: the speaker's cue, then what was said. */
export function LineCell({
  line,
  showTags,
  known,
}: {
  line: ReplayLine;
  showTags: boolean;
  known: Set<string>;
}) {
  const lie = line.marks.some((mark) => mark.label === "lie");
  return (
    <>
      <header className={styles.cue}>
        <TeamMark team={line.team as Team} />
        <span className={styles.who}>{line.speaker}</span>
        <span className={styles.role}>{line.role}</span>
        <a className={styles.ref} href={`#${line.ref}`} aria-label={`Line ${line.ref}`}>
          {line.ref}
        </a>
      </header>
      <p className={styles.said} data-lie={lie || undefined}>
        {line.text}
      </p>
      <Cites line={line} known={known} />
      <p className={styles.meta}>
        {line.reply ? "Free reply." : line.paid > 0 ? `Paid ${plural(line.paid, "token")}.` : null}
        {showTags && line.moves.length > 0 ? ` Moves: ${line.moves.map(moveName).join(", ")}.` : null}
        {lie ? <span className={styles.liemark}>lie</span> : null}
      </p>
    </>
  );
}

export function VoteCell({ vote }: { vote: ReplayVote }) {
  return (
    <>
      <header className={styles.cue}>
        <TeamMark team={vote.team as Team} />
        <span className={styles.who}>{vote.voter}</span>
        <span className={styles.role}>{vote.role}</span>
      </header>
      <p className={styles.vote}>
        {vote.target ? `Votes for ${vote.target}.` : "Abstains."}
        {vote.reason ? ` ${vote.reason}` : ""}
      </p>
    </>
  );
}

export function VoteNote({ vote }: { vote: ReplayVote }) {
  if (!vote.subtext?.note) return null;
  return (
    <aside className={styles.subtext} aria-label={`Private note for ${vote.voter}'s vote`}>
      <p className={styles.note}>{vote.subtext.note}</p>
    </aside>
  );
}

/** Private happenings with no public line beside them: wolf chat and the night. */
export function PrivateCell({ entry }: { entry: ReplayEntry }) {
  if (entry.kind === "wolf_chat") {
    return (
      <aside className={styles.subtext} aria-label="Wolf chat">
        <p className={styles.chat}>
          <TeamMark team="Wolves" /> <b>{entry.speaker}</b> to the other wolf
        </p>
        <p className={styles.note}>{entry.text}</p>
      </aside>
    );
  }
  if (entry.kind === "night") {
    const parts = [
      entry.kill ? `The wolves chose ${entry.kill}.` : "The wolves chose nobody.",
      entry.protect ? `The Doctor protected ${entry.protect}.` : null,
      entry.check ? `The Seer checked ${entry.check}.` : null,
      entry.saved ? "The kill was saved." : null,
    ].filter(Boolean);
    return (
      <aside className={styles.subtext} aria-label="The night">
        <p className={styles.chat}>The night</p>
        <p className={styles.note}>{parts.join(" ")}</p>
      </aside>
    );
  }
  if (entry.kind === "seer_result") {
    return (
      <aside className={styles.subtext} aria-label="Seer result">
        <p className={styles.note}>
          {entry.seer} learns that {entry.target} is a {entry.role}.
        </p>
      </aside>
    );
  }
  return null;
}
