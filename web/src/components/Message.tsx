import type { ReplayLine, ReplayVote } from "@/lib/api";
import { moveName, plural } from "@/lib/format";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import styles from "./Message.module.css";

type Props = {
  id: string;
  entry: ReplayLine | ReplayVote;
  /** Show roles, the lab's findings and the private-note marker. Off is the public view. */
  showRoles: boolean;
  showMoves: boolean;
  selected: boolean;
  dim: boolean;
  /** Every public line by its number, so a cite can show the line it points at. */
  quotes: Map<string, ReplayLine>;
  onSelect: (id: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void;
};

function Bubble() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <path
        d="M3 2.5h10a1.5 1.5 0 0 1 1.5 1.5v6A1.5 1.5 0 0 1 13 11.5H8.4L5 14v-2.5H3A1.5 1.5 0 0 1 1.5 10V4A1.5 1.5 0 0 1 3 2.5Z"
        fill="currentColor"
      />
    </svg>
  );
}

function Reply({ line }: { line: ReplayLine }) {
  return (
    <a className={styles.reply} href={`#${line.ref}`} aria-label={`In reply to ${line.speaker}, line ${line.ref}`}>
      <svg viewBox="0 0 24 12" width="24" height="12" aria-hidden="true" focusable="false">
        <path d="M2 12V6a5 5 0 0 1 5-5h17" fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
      <Avatar name={line.speaker} size={16} />
      <b>{line.speaker}</b>
      <span>{line.text}</span>
    </a>
  );
}

export function Message({
  id,
  entry,
  showRoles,
  showMoves,
  selected,
  dim,
  quotes,
  onSelect,
  onKeyDown,
}: Props) {
  const isLine = entry.kind === "line";
  const name = isLine ? entry.speaker : entry.voter;
  const marks = showRoles ? entry.marks : [];
  const lie = marks.some((mark) => mark.label === "lie");
  const quoted = isLine ? entry.cites.map((c) => quotes.get(c.line)).find((l) => l) : undefined;
  const note = showRoles && entry.subtext;

  function choose(event: React.KeyboardEvent<HTMLElement>) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    } else {
      onKeyDown(event);
    }
  }

  return (
    <article
      id={id}
      className={styles.message}
      data-msg
      data-id={id}
      data-selected={selected || undefined}
      data-dim={dim || undefined}
      data-lie={lie || undefined}
      tabIndex={0}
      aria-current={selected ? "true" : undefined}
      aria-label={`${name}, ${isLine ? `line ${entry.ref}` : "vote"}`}
      onClick={() => onSelect(id)}
      onKeyDown={choose}
    >
      {quoted ? <Reply line={quoted} /> : null}
      <div className={styles.row}>
        <Avatar name={name} />
        <div className={styles.body}>
          <header className={styles.head}>
            <span className={styles.name}>{name}</span>
            {showRoles ? <RoleTag role={entry.role} team={entry.team} /> : null}
            {isLine ? (
              <a className={styles.ref} href={`#${entry.ref}`} aria-label={`Line ${entry.ref}`}>
                {entry.ref}
              </a>
            ) : null}
            {note ? (
              <span className={styles.has} title="Has a private note">
                <Bubble />
                <span className="visually-hidden">Has a private note</span>
              </span>
            ) : null}
          </header>

          {isLine ? (
            <p className={styles.text}>{entry.text}</p>
          ) : (
            <div className={styles.embed}>
              <b>{entry.target ? `Voted for ${entry.target}` : "Abstained"}</b>
              {entry.reason ? <p>{entry.reason}</p> : null}
            </div>
          )}

          <ul className={styles.chips} aria-label="About this message">
            {isLine && showMoves && (entry.reply || entry.paid > 0) ? (
              <li>{entry.reply ? "free reply" : plural(entry.paid, "token")}</li>
            ) : null}
            {isLine && showMoves ? entry.moves.map((move) => <li key={move}>{moveName(move)}</li>) : null}
            {marks
              .filter((mark) => showMoves || mark.label === "lie")
              .map((mark) => (
                <li key={mark.label} data-flag={mark.label === "lie" ? "lie" : undefined}>
                  {moveName(mark.label)}
                </li>
              ))}
          </ul>
        </div>
      </div>
    </article>
  );
}
