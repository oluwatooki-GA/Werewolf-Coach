import { Ballot, Flag, Sun } from "./Icons";
import styles from "./Pill.module.css";

type Props = {
  /** A divider is a heading (a round); the rest are plain lines in the chat. */
  as?: "p" | "h2" | "div";
  /**
   * date: a round divider. morning, removal and end: what happened, each with its own drawn icon.
   * system: any other line. private: the night's secrets. notice: the note at the top.
   */
  tone?: "date" | "system" | "morning" | "removal" | "end" | "private" | "notice";
  id?: string;
  children: React.ReactNode;
};

const ICONS = { morning: Sun, removal: Ballot, end: Flag } as const;

/** The small centred capsule a messenger uses for a date, a system line or a notice. */
export function Pill({ as: Tag = "p", tone = "system", id, children }: Props) {
  const Icon = tone === "morning" || tone === "removal" || tone === "end" ? ICONS[tone] : null;
  return (
    <Tag className={styles.pill} data-tone={tone} id={id}>
      {Icon ? <Icon size={18} /> : null}
      {children}
    </Tag>
  );
}
