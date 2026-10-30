"use client";

import Link from "next/link";
import { useState } from "react";
import type { AdminOverview } from "@/lib/api";
import { ChatAvatar } from "./ChatAvatar";
import { ChatPage } from "./ChatPage";
import styles from "./AdminBoard.module.css";

const dollars = (n: number) => `$${n.toFixed(2)}`;

/**
 * The owner's page: how many games were played here and what they cost. It asks for the admin token
 * (kept only in this page's memory, never stored or put in an address) and shows nothing without it.
 */
export function AdminBoard() {
  const [token, setToken] = useState("");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [problem, setProblem] = useState("");

  async function open(event: React.FormEvent) {
    event.preventDefault();
    setProblem("");
    try {
      const response = await fetch("/api/admin", { headers: { authorization: `Bearer ${token}` } });
      if (response.status === 401) setProblem("That token was not accepted.");
      else if (response.status === 404) setProblem("The admin page is not turned on for this server.");
      else if (!response.ok) setProblem("The server could not give the overview.");
      else {
        setOverview((await response.json()) as AdminOverview);
        setToken("");
      }
    } catch {
      setProblem("The site could not reach the game server.");
    }
  }

  return (
    <ChatPage avatar={<ChatAvatar kind="coach" size={40} />} title="Admin" subtitle="For the owner">
      {overview === null ? (
        <form className={styles.form} onSubmit={open}>
          <label>
            Admin token
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
          </label>
          <button type="submit" disabled={token === ""}>
            Open
          </button>
          {problem ? <p role="alert">{problem}</p> : null}
        </form>
      ) : (
        <Overview overview={overview} />
      )}
    </ChatPage>
  );
}

function Counts({ label, rows }: { label: string; rows: [string, string][] }) {
  return (
    <section className={styles.card} aria-label={label}>
      <h2>{label}</h2>
      <dl>
        {rows.map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Overview({ overview }: { overview: AdminOverview }) {
  const { metrics, recent } = overview;
  return (
    <div className={styles.grid}>
      <p className={styles.line}>
        Play model <b>{overview.play_model || "not set"}</b>, {overview.active_games} being played now.
      </p>
      <Counts
        label="Games played here"
        rows={[
          ["Started", String(metrics.play.started)],
          ["Finished", String(metrics.play.finished)],
          ["Stopped", String(metrics.play.stopped)],
          ["Running now", String(metrics.play.running)],
        ]}
      />
      <Counts
        label="Spend"
        rows={[
          ["Today", dollars(metrics.spend.today)],
          ["In all", dollars(metrics.spend.total)],
          ...Object.entries(metrics.spend.by_day).map(([day, amount]): [string, string] => [day, dollars(amount)]),
        ]}
      />
      <Counts
        label="Stored games"
        rows={[
          ["In all", String(metrics.games.total)],
          ["With a failed call", String(metrics.games.unclean)],
          ...Object.entries(metrics.games.by_source).map(([source, n]): [string, string] => [`From ${source}`, String(n)]),
        ]}
      />
      <section className={styles.card} aria-label="Latest games started">
        <h2>Latest games started</h2>
        <ul>
          {recent.map((play) => (
            <li key={play.id}>
              <span>{new Date(play.created_at * 1000).toLocaleString()}</span>
              <b>{play.status}</b>
              <span>{dollars(play.cost)}</span>
              {play.game_id ? <Link href={`/games/${play.game_id}`}>{play.game_id}</Link> : null}
              {play.reason ? <em>{play.reason}</em> : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
