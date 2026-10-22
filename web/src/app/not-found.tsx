import Link from "next/link";
import { ChannelHeader } from "@/components/ChannelHeader";
import styles from "./notice.module.css";

export default function NotFound() {
  return (
    <>
      <ChannelHeader name="not-found" />
      <div className={styles.page}>
        <h2>There is nothing at this address</h2>
        <p>The game may have been removed, or the link may be mistyped.</p>
        <Link href="/games" className={styles.action}>
          Back to the replays
        </Link>
      </div>
    </>
  );
}
