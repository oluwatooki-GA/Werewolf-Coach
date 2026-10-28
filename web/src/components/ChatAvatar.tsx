import { Cards, Coach, Moon, Seat } from "./Icons";
import { TeamMark } from "./TeamMark";
import styles from "./ChatAvatar.module.css";

type Kind = "welcome" | "strategies" | "coach" | "play" | "Wolves" | "Village";

/** The round picture of a chat in the list and in its header. A game wears its winner's mark. */
export function ChatAvatar({ kind, size = 48 }: { kind: Kind; size?: number }) {
  const icon =
    kind === "welcome" ? <Moon /> : kind === "strategies" ? <Cards /> : kind === "coach" ? <Coach /> : kind === "play" ? <Seat /> : null;
  return (
    <span className={styles.avatar} data-kind={kind} style={{ width: size, height: size }} aria-hidden="true">
      {icon ?? <TeamMark team={kind as "Wolves" | "Village"} />}
    </span>
  );
}
