import { Avatar } from "./Avatar";
import styles from "./Typing.module.css";

/**
 * A bubble that says who is writing, with three dots, like a messenger's "typing".
 * With no name it is the game thinking about who speaks next: same bubble, an empty gutter.
 */
export function Typing({ name }: { name?: string }) {
  return (
    <div className={styles.row} role="status">
      <span className={styles.gutter}>{name ? <Avatar name={name} size={32} /> : null}</span>
      <span className={styles.bubble}>
        <span className={styles.label}>{name ?? "Someone"} is typing</span>
        <span className={styles.dots} aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </span>
    </div>
  );
}
