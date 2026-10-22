import { avatarColor, initial } from "@/lib/people";
import styles from "./Avatar.module.css";

/** A round avatar with the player's initial; the name is always written beside it. */
export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  return (
    <span
      className={styles.avatar}
      style={{ background: avatarColor(name), width: size, height: size, fontSize: size * 0.45 }}
      aria-hidden="true"
    >
      {initial(name)}
    </span>
  );
}
