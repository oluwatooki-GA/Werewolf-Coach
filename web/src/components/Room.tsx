"use client";

import { Fragment, useRef, useState } from "react";
import type { ReplayEntry, ReplayLine, ReplayPlayer, ReplayVote } from "@/lib/api";
import { Avatar } from "./Avatar";
import { Members } from "./Members";
import { Message } from "./Message";
import { Thoughts } from "./Thoughts";
import { TeamMark } from "./TeamMark";
import styles from "./Room.module.css";

type Props = {
  entries: ReplayEntry[];
  players: ReplayPlayer[];
  /** The channel's name and topic. With none, the room has no header (an excerpt). */
  title?: string;
  topic?: string;
  /** A message to select when the page opens, so its private note is already showing. */
  startAt?: string;
  /** An excerpt: no member list and no round dividers. */
  compact?: boolean;
  label: string;
};

type Selectable = ReplayLine | ReplayVote;

function Lock() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <path
        d="M8 1.5a3.5 3.5 0 0 0-3.5 3.5v2H3.8A1.3 1.3 0 0 0 2.5 8.3v5.4a1.3 1.3 0 0 0 1.3 1.3h8.4a1.3 1.3 0 0 0 1.3-1.3V8.3A1.3 1.3 0 0 0 12.2 7H11.5V5A3.5 3.5 0 0 0 8 1.5Zm-2 3.5a2 2 0 1 1 4 0v2H6V5Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function Room({ entries, players, title, topic, startAt, compact = false, label }: Props) {
  const feed = useRef<HTMLDivElement>(null);
  const [roles, setRoles] = useState(true);
  const [moves, setMoves] = useState(true);
  const [selected, setSelected] = useState<string | null>(startAt ?? null);
  const [isolated, setIsolated] = useState<string | null>(null);

  const cast = new Map(players.map((p) => [p.name, p]));
  const quotes = new Map(
    entries.flatMap((e) => (e.kind === "line" ? [[e.ref, e] as [string, ReplayLine]] : [])),
  );
  const ids = entries.map((e, i) => (e.kind === "line" ? e.ref : e.kind === "vote" ? `vote-${i}` : ""));
  const chosen = ids.indexOf(selected ?? "\0");
  const entry = chosen >= 0 ? (entries[chosen] as Selectable) : null;

  function onKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") return setSelected(null);
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const all = [...(feed.current?.querySelectorAll<HTMLElement>("[data-msg]") ?? [])];
    const next = all[all.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      event.preventDefault();
      next.focus();
      setSelected(next.dataset.id ?? null);
    }
  }

  const speaker = (e: ReplayEntry) => (e.kind === "line" ? e.speaker : e.kind === "vote" ? e.voter : "");
  const select = (id: string) => setSelected(id);
  const rounds = [...new Set(entries.map((e) => e.round))].filter((r) => r > 0);

  return (
    <div className={styles.room}>
      <section className={styles.channel} aria-label={label}>
        {title ? (
          <header className={styles.bar}>
            <h1>
              <span aria-hidden="true">#</span> {title}
            </h1>
            {topic ? <p className={styles.topic}>{topic}</p> : null}
            <div className={styles.switches} role="group" aria-label="What to show">
              <label>
                <input type="checkbox" checked={roles} onChange={(e) => setRoles(e.target.checked)} />
                <span>Roles and private notes</span>
              </label>
              <label>
                <input type="checkbox" checked={moves} onChange={(e) => setMoves(e.target.checked)} />
                <span>Moves</span>
              </label>
            </div>
          </header>
        ) : null}

        {title && !compact ? (
          <details className={styles.mobileMembers}>
            <summary>Players ({players.length})</summary>
            <Members players={players} showRoles={roles} isolated={isolated} onIsolate={setIsolated} />
          </details>
        ) : null}

        <div ref={feed} role="feed" aria-label={`${label}, messages`} className={styles.feed}>
          {entries.map((e, index) => {
            const first = index === 0 || entries[index - 1]?.round !== e.round;
            const divider =
              !compact && first && e.round > 0 ? (
                <h2 className={styles.divider} id={`round-${e.round}`}>
                  <span>Round {e.round}</span>
                </h2>
              ) : null;
            const id = ids[index] ?? "";
            const isSelected = id !== "" && id === selected;

            if (e.kind === "direction") {
              return (
                <Fragment key={index}>
                  {divider}
                  <p className={styles.system} data-tone={e.tone}>
                    {e.text}
                  </p>
                </Fragment>
              );
            }
            if (e.kind === "line" || e.kind === "vote") {
              return (
                <Fragment key={index}>
                  {divider}
                  <Message
                    id={id}
                    entry={e}
                    showRoles={roles}
                    showMoves={moves}
                    selected={isSelected}
                    dim={isolated !== null && speaker(e) !== isolated}
                    quotes={quotes}
                    onSelect={select}
                    onKeyDown={onKeyDown}
                  />
                  {isSelected ? (
                    <div className={styles.inline}>
                      <Thoughts entry={e} cast={cast} showRoles={roles} surface="inline" />
                    </div>
                  ) : null}
                </Fragment>
              );
            }
            // wolf chat, the night and the Seer's check: only shown with roles, and marked private
            if (!roles) return <Fragment key={index}>{divider}</Fragment>;
            return (
              <Fragment key={index}>
                {divider}
                {e.kind === "wolf_chat" ? (
                  <div className={styles.wolves} data-dim={isolated !== null && isolated !== e.speaker ? "" : undefined}>
                    <Avatar name={e.speaker} size={32} />
                    <div>
                      <p className={styles.private}>
                        <Lock /> <b>{e.speaker}</b> <TeamMark team="Wolves" word /> only the wolves saw this
                      </p>
                      <p>{e.text}</p>
                    </div>
                  </div>
                ) : (
                  <p className={styles.secret}>
                    <Lock />
                    <span>
                      {e.kind === "night"
                        ? [
                            e.kill ? `The wolves chose ${e.kill}.` : "The wolves chose nobody.",
                            e.protect ? `The Doctor protected ${e.protect}.` : null,
                            e.check ? `The Seer checked ${e.check}.` : null,
                            e.saved ? "The kill was saved." : null,
                          ]
                            .filter(Boolean)
                            .join(" ")
                        : `${e.seer} learns that ${e.target} is a ${e.role}.`}
                    </span>
                  </p>
                )}
              </Fragment>
            );
          })}
        </div>
        {!compact && rounds.length > 0 ? (
          <nav className={styles.jump} aria-label="Jump to a round">
            {rounds.map((r) => (
              <a key={r} href={`#round-${r}`}>
                Round {r}
              </a>
            ))}
          </nav>
        ) : null}
      </section>

      <aside className={styles.panel} aria-label="Details">
        <Thoughts entry={entry} cast={cast} showRoles={roles} surface="panel" />
        {compact ? null : (
          <Members players={players} showRoles={roles} isolated={isolated} onIsolate={setIsolated} />
        )}
      </aside>
    </div>
  );
}
