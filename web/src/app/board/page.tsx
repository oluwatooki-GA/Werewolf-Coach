import type { Metadata } from "next";
import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Chips } from "@/components/Chips";
import { IntervalBar } from "@/components/IntervalBar";
import { Pill } from "@/components/Pill";
import { Embed, Post } from "@/components/Post";
import { TeamMark } from "@/components/TeamMark";
import { api } from "@/lib/api";
import type { Card, CardResult } from "@/lib/api";
import { ENOUGH_GAMES, cardParts, plural, ruleLabel } from "@/lib/format";
import styles from "./board.module.css";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Strategies" };

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
    <ChatPage
      avatar={<ChatAvatar kind="strategies" size={40} />}
      title="Strategies"
      subtitle={ruleLabel(version)}
      actions={
        <Chips
          label="Rule set"
          items={versions.map((v) => ({ href: `/board?rules=${v}`, text: v, current: v === version }))}
        />
      }
    >
      <Pill as="div" tone="notice">
        <p>
          How each strategy card did in the saved games. The bar is the 95% interval for the win rate and the dot is
          what was observed. With fewer than {ENOUGH_GAMES} games, a gap between two cards is not clear yet.
        </p>
      </Pill>

      {shown.length === 0 ? <Pill>No games have been saved under these rules yet.</Pill> : null}

      {ROLES.map((role) => {
        const rows = shown.filter((r) => r.role === role);
        if (rows.length === 0) return null;
        const team = role === "Werewolf" ? "Wolves" : "Village";
        return (
          <section key={role} aria-labelledby={`role-${role}`} className={styles.role}>
            <Pill as="h2" tone="date" id={`role-${role}`}>
              {role === "Werewolf" ? "Werewolves" : `${role}s`}, {plural(rows.length, "card")}
              <span className={styles.team}>
                <TeamMark team={team} word /> win
              </span>
            </Pill>
            {rows.map((row, i) => {
              const parts = cardParts(row.card);
              const card = text.get(row.card);
              return (
                <Post key={row.card} name="Lab" bot first={i === 0}>
                  <p>
                    <b className={styles.name}>{parts.name}</b>, version {parts.version}. {plural(row.games, "game")}.
                  </p>
                  <Embed>
                    <IntervalBar
                      wins={row.wins}
                      games={row.games}
                      enough={row.enough}
                      of={`${team === "Wolves" ? "Wolves" : "The village"} won`}
                    />
                  </Embed>
                  {card ? (
                    <details className={styles.read}>
                      <summary>Read the card</summary>
                      <p className={styles.script}>{card.instructions}</p>
                      <p className={styles.source}>
                        {card.parent ? `Built on ${cardParts(card.parent).name}. ` : ""}
                        {card.source}
                      </p>
                    </details>
                  ) : null}
                </Post>
              );
            })}
          </section>
        );
      })}
    </ChatPage>
  );
}
