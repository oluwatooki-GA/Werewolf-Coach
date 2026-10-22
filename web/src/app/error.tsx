"use client";

import styles from "./notice.module.css";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className={styles.sheet} aria-labelledby="down" role="alert">
      <h1 id="down">The binder is locked</h1>
      <p>
        The site could not reach its data. The API may be starting up or stopped. Wait a moment and
        try again.
      </p>
      <button type="button" className={styles.action} onClick={reset}>
        Try again
      </button>
    </section>
  );
}
