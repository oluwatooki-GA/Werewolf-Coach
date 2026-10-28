import type { ReplayPlayer } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";
import { Avatar } from "./Avatar";
import { TeamMark } from "./TeamMark";
import styles from "./Members.module.css";

type Props = {
  players: ReplayPlayer[];
  /** Roles are hidden until you ask for them: the public view lists names only. */
  showRoles: boolean;
  isolated: string | null;
  onIsolate: (name: string | null) => void;
};

/** Who is at the table. Click a name to follow only their messages. */
export function Members({ players, showRoles, isolated, onIsolate }: Props) {
  return (
    <nav className={styles.members} aria-label="Players">
      <h3>Players, {plural(players.length, "player")}</h3>
      <ul>
        {players.map((p) => (
          <li key={p.name}>
            <button
              type="button"
              aria-pressed={isolated === p.name}
              onClick={() => onIsolate(isolated === p.name ? null : p.name)}
            >
              <Avatar name={p.name} size={28} />
              <b>{p.name}</b>
              {showRoles ? (
                <span className={styles.role} data-team={p.team}>
                  <TeamMark team={p.team} />
                  {p.role}
                </span>
              ) : null}
              {showRoles && p.card ? <small>Strategy: {cardParts(p.card).name}</small> : null}
            </button>
          </li>
        ))}
      </ul>
      <p className={styles.tip}>
        {isolated ? `Following ${isolated}. Click again to see everyone.` : "Click a player to follow only their messages."}
      </p>
    </nav>
  );
}
