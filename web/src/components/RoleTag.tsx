import { roleColor } from "@/lib/people";
import { TeamMark } from "./TeamMark";
import styles from "./RoleTag.module.css";

/** A role next to a name, like a bot tag: the team's drawn mark and the role in words. */
export function RoleTag({ role, team }: { role: string; team: "Village" | "Wolves" }) {
  return (
    <span className={styles.tag} style={{ ["--role" as string]: roleColor(role) }}>
      <TeamMark team={team} />
      {role}
    </span>
  );
}
