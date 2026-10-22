"use client";

import { useState } from "react";
import type { Replay } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";
import { Spread } from "./Spread";
import { TeamMark } from "./TeamMark";
import styles from "./ReplayView.module.css";

export function ReplayView({ replay, startAt }: { replay: Replay; startAt?: string }) {
  const [notes, setNotes] = useState(true);
  const [tags, setTags] = useState(true);
  const rounds = [...new Set(replay.entries.map((e) => e.round))].filter((r) => r > 0);
  const winner = replay.winner === "Wolves" ? "wolves" : "village";

  return (
    <article className={styles.sheet}>
      <div className={styles.bar}>
        <div className={styles.controls} role="group" aria-label="What to show">
          <label className={styles.switch}>
            <input type="checkbox" checked={notes} onChange={(e) => setNotes(e.target.checked)} />
            <span>Private notes</span>
          </label>
          <label className={styles.switch}>
            <input
              type="checkbox"
              checked={tags}
              onChange={(e) => setTags(e.target.checked)}
              disabled={!replay.tagged}
            />
            <span>{replay.tagged ? "Persuasion moves" : "Moves (not tagged)"}</span>
          </label>
          <nav aria-label="Jump to a round" className={styles.rounds}>
            {rounds.map((r) => (
              <a key={r} href={`#round-${r}`}>
                Round {r}
              </a>
            ))}
          </nav>
        </div>
      </div>
      <header className={styles.top}>
        <ul className={styles.cast} aria-label="The players">
          {replay.players.map((p) => (
            <li key={p.name}>
              <TeamMark team={p.team} />
              <b>{p.name}</b>
              <span>{p.role}</span>
              {p.card ? <small>{cardParts(p.card).name}</small> : null}
            </li>
          ))}
        </ul>
      </header>

      <Spread
        entries={replay.entries}
        players={replay.players}
        showNotes={notes}
        showTags={tags}
        startAt={startAt}
        label={`Seed ${replay.seed}: public lines beside private notes`}
      />

      <footer className={styles.verdict}>
        <TeamMark team={replay.winner} />
        <p>
          The {winner} won in {plural(replay.rounds, "round")}. {replay.stats.responses} answers,{" "}
          {replay.stats.rejected} rejected, ${replay.stats.cost.toFixed(3)}.
        </p>
      </footer>
    </article>
  );
}
