import { Avatar } from "./Avatar";
import styles from "./Typing.module.css";

/** "Hal is typing" with three bouncing dots, shown just before that player's message arrives. */
export function Typing({ name }: { name: string }) {
  return (
    <div className={styles.typing} role="status">
      <Avatar name={name} size={28} />
      <span>
        <b>{name}</b> is typing
      </span>
      <span className={styles.dots} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}
