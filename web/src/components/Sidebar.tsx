"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { TeamMark } from "./TeamMark";
import styles from "./Sidebar.module.css";

type Channel = { href: string; label: string; match: string; note?: string; children?: Channel[] };

const CHANNELS: Channel[] = [
  { href: "/games", label: "replays", match: "/games" },
  { href: "/board", label: "strategies", match: "/board" },
  {
    href: "/coach/wolf",
    label: "coach",
    match: "/coach",
    children: [
      { href: "/coach/wolf", label: "wolves", match: "/coach/wolf" },
      { href: "/coach/villager", label: "villagers", match: "/coach/villager" },
    ],
  },
  { href: "/play", label: "play", match: "/play", note: "soon" },
];

function Hash() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d="M6.2 2 5.5 5H2.8v1.6h2.3l-.5 2.8H2v1.6h2.3L3.7 14h1.7l.6-3h2.8l-.6 3h1.7l.6-3H13V9.4h-2.3l.5-2.8H14V5h-2.4l.6-3h-1.7l-.6 3H7.1l.6-3H6.2Zm.6 4.6h2.8l-.5 2.8H6.3l.5-2.8Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function Sidebar() {
  const path = usePathname();
  const on = (channel: Channel) => path === channel.match || path.startsWith(`${channel.match}/`);
  return (
    <aside className={styles.side}>
      <Link href="/" className={styles.server} aria-label="Werewolf Coach, home">
        <span className={styles.marks} aria-hidden="true">
          <TeamMark team="Wolves" />
          <TeamMark team="Village" />
        </span>
        Werewolf Coach
      </Link>
      <nav aria-label="Channels" className={styles.nav}>
        <ul>
          {CHANNELS.map((channel) => (
            <li key={channel.href}>
              <Link
                href={channel.href}
                className={styles.channel}
                aria-current={path === channel.match ? "page" : undefined}
                data-active={on(channel) || undefined}
              >
                <Hash />
                <span>{channel.label}</span>
                {channel.note ? <small>{channel.note}</small> : null}
              </Link>
              {channel.children && on(channel) ? (
                <ul className={styles.sub}>
                  {channel.children.map((child) => (
                    <li key={child.href}>
                      <Link
                        href={child.href}
                        className={styles.channel}
                        aria-current={on(child) ? "page" : undefined}
                        data-active={on(child) || undefined}
                      >
                        <span>{child.label}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </nav>
      <p className={styles.foot}>Every player here is an AI agent.</p>
    </aside>
  );
}
