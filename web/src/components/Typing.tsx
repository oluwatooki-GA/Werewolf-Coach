import { Avatar } from "./Avatar";
import styles from "./Typing.module.css";

/** A bubble with three dots while a player is writing, like a messenger's "typing". */
export function Typing({ name }: { name: string }) {
  return (
    <div className={styles.row} role="status">
      <span className={styles.gutter}>
        <Avatar name={name} size={32} />
      </span>
      <span className={styles.bubble} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="visually-hidden">{name} is typing</span>
    </div>
  );
}
