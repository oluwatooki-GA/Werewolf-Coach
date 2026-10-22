"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import type { ReplayEntry, ReplayPlayer } from "@/lib/api";
import { blocks } from "@/lib/replay";
import { LineCell, PrivateCell, SubtextCell, VoteCell, VoteNote, type Cast } from "./Cells";
import styles from "./Spread.module.css";

type Props = {
  entries: ReplayEntry[];
  players: ReplayPlayer[];
  /** Show the facing page: private notes, wolf chat, the night. */
  showNotes: boolean;
  /** Show the persuasion moves the tagger found, beside each line's cost. */
  showTags?: boolean;
  /** Round headings. Off for an excerpt. */
  acts?: boolean;
  /** A line to highlight when the page opens. */
  startAt?: string;
  /** No page shadow or rounded corners: the spread sits inside a larger sheet. */
  flat?: boolean;
  label: string;
};

const GLOW_MS = 2600;

export function Spread({
  entries,
  players,
  showNotes,
  showTags = true,
  acts = true,
  startAt,
  flat = false,
  label,
}: Props) {
  const root = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState<string | null>(startAt ?? null);
  const [fading, setFading] = useState<string | null>(null);

  // The line you leave keeps a glow for a moment, like a worked light going down.
  useEffect(() => {
    if (!fading) return;
    const timer = setTimeout(() => setFading(null), GLOW_MS);
    return () => clearTimeout(timer);
  }, [fading]);

  const cast: Cast = new Map(players.map((p) => [p.name, p]));
  const known = new Set(entries.flatMap((e) => (e.kind === "line" ? [e.ref] : [])));

  function visit(ref: string) {
    if (ref === now) return;
    setFading(now);
    setNow(ref);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const lines = [...(root.current?.querySelectorAll<HTMLElement>("[data-line]") ?? [])];
    const next = lines[lines.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  const items = blocks(entries);
  return (
    <div
      ref={root}
      className={`${styles.spread} ${flat ? styles.flat : ""}`}
      role="group"
      aria-label={label}
    >
      {items.map((entry, index) => {
        const opensRound = entry.round !== (items[index - 1]?.round ?? 0);
        const heading =
          acts && opensRound ? (
            <h2 className={styles.act} id={`round-${entry.round}`}>
              Round {entry.round}
            </h2>
          ) : null;

        if (entry.kind === "direction") {
          return (
            <Fragment key={index}>
              {heading}
              <p className={styles.direction} data-tone={entry.tone}>
                ({entry.text})
              </p>
            </Fragment>
          );
        }
        if (entry.kind === "private") {
          if (!showNotes) return <Fragment key={index}>{heading}</Fragment>;
          return (
            <Fragment key={index}>
              {heading}
              <div className={styles.right} aria-hidden="true" />
              <div className={styles.left}>
                {entry.entries.map((part, i) => (
                  <PrivateCell key={i} entry={part} />
                ))}
              </div>
            </Fragment>
          );
        }
        if (entry.kind === "vote") {
          return (
            <Fragment key={index}>
              {heading}
              <div className={styles.right}>
                <VoteCell vote={entry} />
              </div>
              <div className={styles.left}>{showNotes ? <VoteNote vote={entry} /> : null}</div>
            </Fragment>
          );
        }
        if (entry.kind !== "line") return <Fragment key={index}>{heading}</Fragment>;
        const glow = entry.ref === now ? "now" : entry.ref === fading ? "fade" : undefined;
        return (
          <Fragment key={index}>
            {heading}
            <article
              className={styles.right}
              id={entry.ref}
              data-line
              data-team={entry.team}
              data-glow={glow}
              tabIndex={0}
              aria-label={`${entry.speaker}, line ${entry.ref}`}
              onFocus={() => visit(entry.ref)}
              onClick={() => visit(entry.ref)}
              onKeyDown={onKeyDown}
            >
              <LineCell line={entry} showTags={showTags} known={known} />
            </article>
            <div className={styles.left} data-glow={glow}>
              {showNotes ? <SubtextCell line={entry} cast={cast} /> : null}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
