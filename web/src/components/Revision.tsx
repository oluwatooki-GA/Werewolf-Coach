import { sentences } from "@/lib/format";
import styles from "./Revision.module.css";

type Props = {
  /** The instructions of the card the coach started from, if the site has them. */
  base: string | null;
  /** "- sentence" for a cut and "+ sentence" for an addition, as the coach recorded them. */
  changes: string[];
};

/**
 * A card as a marked-up script page: the sentences the coach kept stay as they were, the ones it
 * cut are struck through in red, and what it added is inserted in blue after a caret. Marks are
 * lines and a caret as well as colour, so they read without it.
 */
export function Revision({ base, changes }: Props) {
  const cut = new Set(changes.filter((c) => c.startsWith("- ")).map((c) => c.slice(2)));
  const added = changes.filter((c) => c.startsWith("+ ")).map((c) => c.slice(2));
  const kept = base ? sentences(base) : [];
  // Without the base text, still show what was cut.
  const orphans = base ? [] : [...cut];

  return (
    <div className={styles.page}>
      <p className={styles.script}>
        {kept.map((s) =>
          cut.has(s) ? (
            <del key={s} className={styles.cut}>
              {s}{" "}
            </del>
          ) : (
            <span key={s}>{s} </span>
          ),
        )}
        {orphans.map((s) => (
          <del key={s} className={styles.cut}>
            {s}{" "}
          </del>
        ))}
        {added.map((s) => (
          <ins key={s} className={styles.add}>
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" focusable="false">
              <path d="M5 1.5 9 8.5H1Z" fill="none" stroke="currentColor" strokeWidth="1.4" />
            </svg>
            <span className="visually-hidden">Added: </span>
            {s}{" "}
          </ins>
        ))}
      </p>
      <p className={styles.legend}>Struck through: cut. Marked with a caret: added by the coach.</p>
    </div>
  );
}
