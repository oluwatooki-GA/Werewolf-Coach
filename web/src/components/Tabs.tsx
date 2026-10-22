"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TeamMark } from "./TeamMark";
import styles from "./Tabs.module.css";

const TABS = [
  { href: "/games", label: "Replays", gel: 1, match: "/games" },
  { href: "/board", label: "Strategies", gel: 0, match: "/board" },
  { href: "/coach/wolf", label: "Coach", gel: 3, match: "/coach" },
  { href: "/play", label: "Play", gel: 5, match: "/play", note: "soon" },
] as const;

export function Tabs() {
  const path = usePathname();
  return (
    <header className={`on-house ${styles.header}`}>
      <Link href="/" className={styles.wordmark} aria-label="Werewolf Coach, home">
        <span className={styles.marks} aria-hidden="true">
          <TeamMark team="Wolves" />
          <TeamMark team="Village" />
        </span>
        Werewolf Coach
      </Link>
      <nav aria-label="Sections" className={styles.nav}>
        <ul className={styles.tabs}>
          {TABS.map((tab) => {
            const active = path === tab.match || path.startsWith(`${tab.match}/`);
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  className={styles.tab}
                  style={{ ["--gel" as string]: `var(--gel-${tab.gel})` }}
                  aria-current={active ? "page" : undefined}
                >
                  {tab.label}
                  {"note" in tab ? <span className={styles.note}>{tab.note}</span> : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
