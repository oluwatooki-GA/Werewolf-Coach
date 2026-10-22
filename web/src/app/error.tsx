"use client";

import { ChannelHeader } from "@/components/ChannelHeader";
import styles from "./notice.module.css";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <>
      <ChannelHeader name="connection-lost" />
      <div className={styles.page} role="alert">
        <h2>The site could not reach its data</h2>
        <p>The API may be starting up or stopped. Wait a moment and try again.</p>
        <button type="button" className={styles.action} onClick={reset}>
          Try again
        </button>
      </div>
    </>
  );
}
