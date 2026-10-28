import type { ReplayPlayer } from "@/lib/api";
import { plural } from "@/lib/format";
import { roleColor } from "@/lib/people";
import { Avatar } from "./Avatar";
import { TeamMark } from "./TeamMark";
import styles from "./Members.module.css";

type Props = {
  players: ReplayPlayer[];
  /** Roles are hidden until you ask for them: the public view lists names only. */
  showRoles: boolean;
  /** Who has left the game by now, and how. */
  out: ReadonlyMap<string, string>;
  /** Tapping a name opens that player's card. */
  onOpen: (name: string) => void;
};

/** Who is at the table. Tap a name to see their strategy card. */
export function Members({ players, showRoles, out, onOpen }: Props) {
  return (
    <nav className={styles.members} aria-label="Players">
      <h3>Players, {plural(players.length, "player")}</h3>
      <ul>
        {players.map((p) => (
          <li key={p.name}>
            <button type="button" data-out={out.has(p.name) || undefined} onClick={() => onOpen(p.name)}>
              <Avatar name={p.name} size={32} out={out.has(p.name)} />
              <b>{p.name}</b>
              {showRoles ? (
                <span className={styles.role} style={{ color: roleColor(p.role) }}>
                  <TeamMark team={p.team} decorative />
                  {p.role}
                </span>
              ) : null}
              {out.has(p.name) ? <small>{out.get(p.name)}</small> : null}
            </button>
          </li>
        ))}
      </ul>
      <p className={styles.tip}>Tap a player to see their strategy card.</p>
    </nav>
  );
}
