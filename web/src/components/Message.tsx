import type { ReplayLine, ReplayVote } from "@/lib/api";
import { moveName, plural } from "@/lib/format";
import { avatarColor } from "@/lib/people";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import styles from "./Message.module.css";

export type Side = "in" | "out";

type Props = {
  id: string;
  entry: ReplayLine | ReplayVote;
  /** Outgoing bubbles sit on the right in amber: the player being watched, or the wolves. */
  side: Side;
  /** First bubble of a run by the same player: it gets the name, the avatar and the tail. */
  first: boolean;
  /** Show the name above the bubble. Off for the watched player, whose messages are "yours". */
  named: boolean;
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

/** The line a message replies to, quoted inside the bubble like a reply in a messenger. */
function Quote({ line }: { line: ReplayLine }) {
  return (
    <a className={styles.quote} href={`#${line.ref}`} aria-label={`In reply to ${line.speaker}, line ${line.ref}`}>
      <i style={{ background: avatarColor(line.speaker) }} aria-hidden="true" />
      <span>
        <b style={{ color: avatarColor(line.speaker) }}>{line.speaker}</b>
        <span>{line.text}</span>
      </span>
    </a>
  );
}

export function Message({
  id,
  entry,
  side,
  first,
  named,
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
  const chips = [
    ...(isLine && showMoves && (entry.reply || entry.paid > 0)
      ? [{ key: "paid", text: entry.reply ? "free reply" : plural(entry.paid, "token"), flag: false }]
      : []),
    ...(isLine && showMoves ? entry.moves.map((move) => ({ key: move, text: moveName(move), flag: false })) : []),
    ...marks
      .filter((mark) => showMoves || mark.label === "lie")
      .map((mark) => ({ key: mark.label, text: moveName(mark.label), flag: mark.label === "lie" })),
  ];

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
      className={styles.row}
      data-msg
      data-id={id}
      data-side={side}
      data-first={first || undefined}
      data-selected={selected || undefined}
      data-dim={dim || undefined}
      data-lie={lie || undefined}
      tabIndex={0}
      aria-current={selected ? "true" : undefined}
      aria-label={`${name}, ${isLine ? `line ${entry.ref}` : "vote"}`}
      onClick={() => onSelect(id)}
      onKeyDown={choose}
    >
      {side === "in" ? <span className={styles.gutter}>{first ? <Avatar name={name} size={32} /> : null}</span> : null}
      <div className={styles.bubble}>
        {first && named ? (
          <header className={styles.head}>
            <span className={styles.name} style={{ color: side === "in" ? avatarColor(name) : undefined }}>
              {name}
            </span>
            {showRoles ? <RoleTag role={entry.role} team={entry.team} /> : null}
          </header>
        ) : null}
        {quoted ? <Quote line={quoted} /> : null}

        {isLine ? (
          <p className={styles.text}>{entry.text}</p>
        ) : (
          <div className={styles.vote}>
            <b>{entry.target ? `Voted for ${entry.target}` : "Abstained"}</b>
            {entry.reason ? <p>{entry.reason}</p> : null}
          </div>
        )}

        <footer className={styles.foot}>
          <ul className={styles.chips} aria-label="About this message">
            {chips.map((chip) => (
              <li key={chip.key} data-flag={chip.flag ? "lie" : undefined}>
                {chip.text}
              </li>
            ))}
          </ul>
          <span className={styles.meta}>
            {note ? (
              <span className={styles.has} title="Has a private note">
                <Bubble />
                <span className="visually-hidden">Has a private note</span>
              </span>
            ) : null}
            {isLine ? (
              <a href={`#${entry.ref}`} aria-label={`Line ${entry.ref}`}>
                {entry.ref}
              </a>
            ) : null}
          </span>
        </footer>
      </div>
    </article>
  );
}
