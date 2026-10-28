import styles from "./Pill.module.css";

type Props = {
  /** A divider is a heading (a round); the rest are plain lines in the chat. */
  as?: "p" | "h2" | "div";
  tone?: "date" | "system" | "private" | "notice" | "end";
  id?: string;
  children: React.ReactNode;
};

/** The small centred capsule a messenger uses for a date, a system line or a notice. */
export function Pill({ as: Tag = "p", tone = "system", id, children }: Props) {
  return (
    <Tag className={styles.pill} data-tone={tone} id={id}>
      {children}
    </Tag>
  );
}
