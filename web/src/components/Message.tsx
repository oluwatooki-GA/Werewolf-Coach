import type { ReplayLine } from "@/lib/api";
import { markName, moveName, plural } from "@/lib/format";
import { avatarColor } from "@/lib/people";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import styles from "./Message.module.css";

export type Side = "in" | "out";

type Props = {
  id: string;
  entry: ReplayLine;
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
  /** Tapping the avatar or the name opens that player's card. */
  onPlayer: (name: string) => void;
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
    <a className={styles.quote} href={`#${line.ref}`} aria-label={`In reply to ${line.speaker}: ${line.text}`}>
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
  onPlayer,
}: Props) {
  const name = entry.speaker;
  const marks = showRoles ? entry.marks : [];
  const lie = marks.some((mark) => mark.label === "lie");
  const quoted = entry.cites.map((c) => quotes.get(c.line)).find((l) => l);
  const note = showRoles && entry.subtext;
  const chips = [
    ...(showMoves && (entry.reply || entry.paid > 0)
      ? [{ key: "paid", text: entry.reply ? "free reply" : plural(entry.paid, "token"), flag: false }]
      : []),
    ...(showMoves ? entry.moves.map((move) => ({ key: move, text: moveName(move), flag: false })) : []),
    ...marks
      .filter((mark) => showMoves || mark.label === "lie")
      .map((mark) => ({ key: mark.label, text: markName(mark.label), flag: mark.label === "lie" })),
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
      aria-label={`${name}, round ${entry.round}, message ${entry.ref.split("-")[1] ?? ""}`}
      onClick={() => onSelect(id)}
      onKeyDown={choose}
    >
      {side === "in" ? (
        <span className={styles.gutter}>
          {first ? (
            <button type="button" className={styles.person} aria-label={`${name}: show their card`} onClick={(e) => { e.stopPropagation(); onPlayer(name); }}>
              <Avatar name={name} size={32} />
            </button>
          ) : null}
        </span>
      ) : null}
      <div className={styles.bubble}>
        {first && named ? (
          <header className={styles.head}>
            <button
              type="button"
              className={styles.name}
              style={{ color: side === "in" ? avatarColor(name) : undefined }}
              onClick={(e) => {
                e.stopPropagation();
                onPlayer(name);
              }}
            >
              {name}
            </button>
            {showRoles ? <RoleTag role={entry.role} team={entry.team} /> : null}
          </header>
        ) : null}
        {quoted ? <Quote line={quoted} /> : null}

        <p className={styles.text}>{entry.text}</p>

        {chips.length > 0 || note ? (
          <footer className={styles.foot}>
            <ul className={styles.chips} aria-label="About this message">
              {chips.map((chip) => (
                <li key={chip.key} data-flag={chip.flag ? "lie" : undefined}>
                  {chip.text}
                </li>
              ))}
            </ul>
            {note ? (
              <span className={styles.has} title="Has a private note. Tap to read it.">
                <Bubble />
                <span className="visually-hidden">Has a private note</span>
              </span>
            ) : null}
          </footer>
        ) : null}
      </div>
    </article>
  );
}
