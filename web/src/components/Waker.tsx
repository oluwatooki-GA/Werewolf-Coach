"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import styles from "./Waker.module.css";

const POLL_MS = 3000;
const GIVE_UP_MS = 120_000;

type Props = {
  /** What to do once the API is up. By default the page is reloaded so it shows the real data. */
  onUp?: () => void;
  /** More to say under the notice, such as what is being shown meanwhile. */
  children?: React.ReactNode;
};

/**
 * Says the API is waking up and asks the site every few seconds whether it is awake yet. A free-plan
 * API that has been idle takes up to a minute to start, and each ask keeps that start going.
 */
export function Waker({ onUp, children }: Props) {
  const router = useRouter();
  const [up, setUp] = useState(false);
  const [late, setLate] = useState(false);
  const whenUp = useRef<() => void>(() => {});
  useEffect(() => {
    whenUp.current = onUp ?? (() => router.refresh());
  });

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const started = Date.now();
    const ask = async () => {
      let awake = false;
      try {
        const response = await fetch("/api/wake", { cache: "no-store" });
        awake = ((await response.json()) as { up?: boolean }).up === true;
      } catch {
        // the site itself did not answer; try again
      }
      if (stopped) return;
      if (awake) {
        setUp(true);
        whenUp.current();
        return;
      }
      if (Date.now() - started > GIVE_UP_MS) setLate(true);
      timer = window.setTimeout(ask, POLL_MS);
    };
    void ask();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <div role="status" className={styles.wake}>
      <p>
        {up
          ? "The server is awake. Loading everything now."
          : late
            ? "The server is still not answering. It may be stopped. This page keeps trying."
            : "The server is waking up. This takes up to a minute."}
      </p>
      {children ? <p>{children}</p> : null}
    </div>
  );
}
