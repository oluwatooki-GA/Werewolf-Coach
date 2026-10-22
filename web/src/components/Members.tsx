import type { ReplayPlayer } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import styles from "./Members.module.css";

type Props = {
  players: ReplayPlayer[];
  /** Roles are hidden until you ask for them: the public view groups everyone as players. */
  showRoles: boolean;
  isolated: string | null;
  onIsolate: (name: string | null) => void;
};

/** The member list, grouped by team like roles in a chat server. Click a name to follow them. */
export function Members({ players, showRoles, isolated, onIsolate }: Props) {
  const groups = showRoles
    ? (["Wolves", "Village"] as const).map((team) => ({
        title: team,
        people: players.filter((p) => p.team === team),
      }))
    : [{ title: "Players" as const, people: players }];

  return (
    <nav className={styles.members} aria-label="Players">
      {groups.map((group) => (
        <section key={group.title}>
          <h3>
            {group.title}, {plural(group.people.length, "player")}
          </h3>
          <ul>
            {group.people.map((p) => (
              <li key={p.name}>
                <button
                  type="button"
                  aria-pressed={isolated === p.name}
                  onClick={() => onIsolate(isolated === p.name ? null : p.name)}
                >
                  <Avatar name={p.name} size={32} />
                  <span className={styles.who}>
                    <b>{p.name}</b>
                    {showRoles ? (
                      <>
                        <RoleTag role={p.role} team={p.team} />
                        {p.card ? <small>{cardParts(p.card).name}</small> : null}
                      </>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className={styles.tip}>
        {isolated ? `Following ${isolated}. Click again to see everyone.` : "Click a player to follow only their messages."}
      </p>
    </nav>
  );
}
