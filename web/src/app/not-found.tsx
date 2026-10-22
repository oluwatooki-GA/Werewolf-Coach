import Link from "next/link";
import styles from "./notice.module.css";

export default function NotFound() {
  return (
    <section className={styles.sheet} aria-labelledby="missing">
      <h1 id="missing">Page not in the binder</h1>
      <p>
        There is nothing at this address. The game may have been removed, or the link may be
        mistyped.
      </p>
      <Link href="/games" className={styles.action}>
        Back to the replays
      </Link>
    </section>
  );
}
