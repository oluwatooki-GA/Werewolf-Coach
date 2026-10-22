import type { Metadata } from "next";
import Link from "next/link";
import { ChannelHeader } from "@/components/ChannelHeader";
import { IntervalBar } from "@/components/IntervalBar";
import { TeamMark } from "@/components/TeamMark";
import { api } from "@/lib/api";
import type { Card, CardResult } from "@/lib/api";
import { ENOUGH_GAMES, cardParts, plural, ruleLabel } from "@/lib/format";
import styles from "./board.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Strategy board" };

const ROLES = ["Werewolf", "Villager", "Seer", "Doctor"] as const;

export default async function Board({ searchParams }: { searchParams: Promise<{ rules?: string }> }) {
  const { rules } = await searchParams;
  const [results, cards] = await Promise.all([
    api<CardResult[]>("/results"),
    api<Card[]>("/strategies"),
  ]);

  // Rule versions are never pooled: a card is judged under the rules it was played under.
  const versions = [...new Set(results.map((r) => r.rule_version))].sort();
  const busiest = versions
    .map((v) => ({ v, n: results.filter((r) => r.rule_version === v).reduce((s, r) => s + r.games, 0) }))
    .sort((a, b) => b.n - a.n)[0]?.v;
  const version = versions.includes(rules ?? "") ? (rules as string) : (busiest ?? "v1");
  const shown = results.filter((r) => r.rule_version === version);
  const text = new Map(cards.map((c) => [`${c.id}@${c.version}`, c]));

  return (
    <>
      <ChannelHeader
        name="strategies"
        topic={`How each card did in the saved games. A bar is the 95% interval for the win rate and the dot is what was observed. With fewer than ${ENOUGH_GAMES} games a gap between two cards is not clear yet.`}
      />
      <div className={styles.page}>
        <nav className={styles.versions} aria-label="Rule set">
          {versions.map((v) => (
            <Link
              key={v}
              href={`/board?rules=${v}`}
              className={styles.pill}
              aria-current={v === version ? "true" : undefined}
            >
              {v}
            </Link>
          ))}
          <span>{ruleLabel(version)}</span>
        </nav>

        {shown.length === 0 ? (
          <p className={styles.empty}>No games have been saved under these rules yet.</p>
        ) : null}

        {ROLES.map((role) => {
          const rows = shown.filter((r) => r.role === role);
          if (rows.length === 0) return null;
          const team = role === "Werewolf" ? "Wolves" : "Village";
          return (
            <section key={role} className={styles.role} aria-labelledby={`role-${role}`}>
              <h2 id={`role-${role}`}>
                {role === "Werewolf" ? "Werewolves" : `${role}s`}
                <span>
                  {plural(rows.length, "card")}, <TeamMark team={team} word /> win
                </span>
              </h2>
              <ol className={styles.cards}>
                {rows.map((row) => {
                  const parts = cardParts(row.card);
                  const card = text.get(row.card);
                  return (
                    <li key={row.card}>
                      <div className={styles.line}>
                        <h3>
                          {parts.name}
                          <small>version {parts.version}</small>
                        </h3>
                        <p className={styles.games}>{plural(row.games, "game")}</p>
                        <IntervalBar
                          wins={row.wins}
                          games={row.games}
                          enough={row.enough}
                          of={`${team === "Wolves" ? "Wolves" : "The village"} won`}
                        />
                      </div>
                      {card ? (
                        <details>
                          <summary>Read the card</summary>
                          <p className={styles.script}>{card.instructions}</p>
                          <p className={styles.source}>
                            {card.parent ? `Built on ${cardParts(card.parent).name}. ` : ""}
                            {card.source}
                          </p>
                        </details>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </section>
          );
        })}
      </div>
    </>
  );
}
