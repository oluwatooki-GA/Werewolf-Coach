import { Avatar } from "./Avatar";
import styles from "./Typing.module.css";

/**
 * A bubble with three dots while a player is writing, like a messenger's "typing".
 * With no name it is the game thinking about who speaks next: same bubble, an empty gutter.
 */
export function Typing({ name }: { name?: string }) {
  return (
    <div className={styles.row} role="status">
      <span className={styles.gutter}>{name ? <Avatar name={name} size={32} /> : null}</span>
      <span className={styles.bubble} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="visually-hidden">{name ?? "Someone"} is typing</span>
    </div>
  );
}
