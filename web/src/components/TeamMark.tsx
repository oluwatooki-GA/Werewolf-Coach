import styles from "./TeamMark.module.css";

type Team = "Village" | "Wolves";

/**
 * A team is never shown by colour alone: wolves are a filled triangle, the village an open
 * circle, and the word can follow. The mark itself is decorative, so the word is the label.
 */
export function TeamMark({ team, word = false }: { team: Team; word?: boolean }) {
  return (
    <span className={styles.mark} data-team={team}>
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" focusable="false">
        {team === "Wolves" ? (
          <path d="M6 1.2 11 10.6H1Z" fill="currentColor" />
        ) : (
          <circle cx="6" cy="6" r="4.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
        )}
      </svg>
      {word ? <span>{team === "Wolves" ? "Wolves" : "Village"}</span> : <span className="visually-hidden">{team}</span>}
    </span>
  );
}
