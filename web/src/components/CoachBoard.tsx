"use client";

import { useState } from "react";
import type { Card, CardResult, Generation } from "@/lib/api";
import { cardParts, plural, ruleLabel } from "@/lib/format";
import { roleColor } from "@/lib/people";
import { CardGraph } from "./CardGraph";
import { ChatAvatar } from "./ChatAvatar";
import { ChatHeader } from "./ChatHeader";
import { Chips } from "./Chips";
import { CoachThoughts } from "./CoachThoughts";
import { Back, Close } from "./Icons";
import { IntervalBar } from "./IntervalBar";
import styles from "./CoachBoard.module.css";

type Props = {
  side: string;
  label: string;
  sides: { id: string; label: string }[];
  /** Every card this side can play. */
  cards: Card[];
  generations: Generation[];
  /** How each card did in the saved games, by rule version. */
  results: CardResult[];
};

/** The card whose details are open: a node of the tree, or the lone card picked from the list. */
type Picked = { id: string; ref: string | null; gen: number | null };

const ROLE_ORDER = ["Werewolf", "Villager", "Seer", "Doctor"];
const ref = (c: Card) => `${c.id}@${c.version}`;

/** One card's text, where it came from, and how it did in the saved games. */
function CardInfo({
  card,
  results,
}: {
  card: Card | undefined;
  results: CardResult[];
}) {
  if (!card)
    return (
      <p className={styles.hint}>The text of this card is not on the site.</p>
    );
  const team = card.role === "Werewolf" ? "Wolves" : "The village";
  return (
    <section
      className={styles.card}
      aria-label={`${cardParts(card.id).name}, the card`}
    >
      <h3>{cardParts(card.id).name}</h3>
      <p className={styles.meta}>
        <span style={{ color: roleColor(card.role) }}>{card.role}</span> card,
        version {card.version}
      </p>
      {card.summary ? <p className={styles.summary}>{card.summary}</p> : null}
      <p className={styles.script}>{card.instructions}</p>
      <p className={styles.source}>
        {card.parent ? `Built on ${cardParts(card.parent).name}. ` : ""}
        {card.source}
      </p>
      <h4>How it did in the saved games</h4>
      {results.length === 0 ? (
        <p className={styles.hint}>No saved game used this card yet.</p>
      ) : (
        <ul className={styles.results}>
          {results.map((r) => (
            <li key={r.rule_version}>
              <span>{ruleLabel(r.rule_version)}</span>
              <IntervalBar
                wins={r.wins}
                games={r.games}
                enough={r.enough}
                of={`${team} won`}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * The coach, as cards. First the cards it can start from; pick one and the cards the coach built
 * from it appear as a family tree; pick any card and its details open on the side, with the
 * coach's own thoughts when the coach wrote it.
 */
export function CoachBoard({
  side,
  label,
  sides,
  cards,
  generations,
  results,
}: Props) {
  const [root, setRoot] = useState<string | null>(null);
  const [picked, setPicked] = useState<Picked | null>(null);

  const byRef = new Map(cards.map((c) => [ref(c), c]));
  const start = generations[0]?.champion_before ?? null;
  const champion = generations.at(-1)?.champion_after ?? start;
  const coachMade = new Set(
    generations
      .map((g) => g.challenger_card)
      .filter((c): c is string => Boolean(c)),
  );
  const available = cards.filter((c) => !coachMade.has(ref(c)));
  const roles = ROLE_ORDER.filter((r) => available.some((c) => c.role === r));
  const rootCard = root ? byRef.get(root) : undefined;
  const open = picked !== null;
  const gen =
    picked?.gen != null
      ? generations.find((g) => g.number === picked.gen)
      : undefined;
  const pickedCard = picked?.ref ? byRef.get(picked.ref) : undefined;

  function choose(card: Card) {
    setRoot(ref(card));
    setPicked(null);
  }

  return (
    <div className={styles.board} data-panel={open ? "open" : "closed"}>
      <section className={styles.main} aria-label="The coach's cards">
        <ChatHeader
          avatar={<ChatAvatar kind="coach" size={40} />}
          title={`Coach: ${label.toLowerCase()}`}
          subtitle={
            rootCard
              ? `Cards built from ${cardParts(rootCard.id).name}`
              : "Pick a card to see what the coach built from it"
          }
          actions={
            <Chips
              label="Which side"
              items={sides.map((s) => ({
                href: `/coach/${s.id}`,
                text: s.label,
                current: s.id === side,
              }))}
            />
          }
        />

        <div className={styles.canvas}>
          {root === null ? (
            <div className={styles.cards}>
              {roles.map((role) => (
                <section key={role} aria-labelledby={`cards-${role}`}>
                  <h2 id={`cards-${role}`} style={{ color: roleColor(role) }}>
                    {role === "Werewolf" ? "Werewolf cards" : `${role} cards`}
                  </h2>
                  <ul className={styles.grid}>
                    {available
                      .filter((c) => c.role === role)
                      .map((c) => {
                        const built = ref(c) === start ? generations.length : 0;
                        return (
                          <li key={ref(c)}>
                            <button
                              type="button"
                              className={styles.tile}
                              data-champion={ref(c) === champion || undefined}
                              onClick={() => choose(c)}
                            >
                              <b>{cardParts(c.id).name}</b>
                              <small>version {c.version}</small>
                              {c.summary ? <span>{c.summary}</span> : null}
                              <em>
                                {ref(c) === champion
                                  ? "Current champion. "
                                  : ""}
                                {built > 0
                                  ? `The coach built ${plural(built, "card")} from it.`
                                  : "The coach has not built on it yet."}
                              </em>
                            </button>
                          </li>
                        );
                      })}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <div className={styles.tree}>
              <button
                type="button"
                className={styles.back}
                onClick={() => {
                  setRoot(null);
                  setPicked(null);
                }}
              >
                <Back size={18} /> All cards
              </button>
              {root === start && generations.length > 0 ? (
                <CardGraph
                  generations={generations}
                  picked={picked?.id ?? null}
                  onPick={(node) => setPicked(node)}
                />
              ) : (
                <div className={styles.lone}>
                  <button
                    type="button"
                    className={styles.tile}
                    data-champion={root === champion || undefined}
                    aria-pressed={picked?.id === `root:${root}`}
                    onClick={() =>
                      setPicked({ id: `root:${root}`, ref: root, gen: null })
                    }
                  >
                    <b>{rootCard ? cardParts(rootCard.id).name : root}</b>
                    <small>version {rootCard?.version}</small>
                    {rootCard?.summary ? <span>{rootCard.summary}</span> : null}
                  </button>
                  <p className={styles.hint}>
                    The coach has not built on this card yet. Tap it for the
                    card itself.
                  </p>
                </div>
              )}
              <p className={styles.hint}>
                Top line: the champion. Below it: cards the coach tried and
                dropped. Tap any card for its details.
              </p>
            </div>
          )}
        </div>
      </section>

      <aside className={styles.info} aria-label="Details" hidden={!open}>
        <header className={styles.infohead}>
          <button
            type="button"
            className={styles.icon}
            aria-label="Close"
            onClick={() => setPicked(null)}
          >
            <Close />
          </button>
          <h2>
            {picked
              ? picked.ref
                ? cardParts(picked.ref).name
                : "No valid card"
              : "Details"}
          </h2>
        </header>
        <div className={styles.infobody}>
          {picked ? (
            <>
              {picked.ref ? (
                <CardInfo
                  card={pickedCard}
                  results={results.filter((r) => r.card === picked.ref)}
                />
              ) : null}
              {gen ? (
                <CoachThoughts
                  key={picked.id}
                  gen={gen}
                  base={byRef.get(gen.champion_before)?.instructions ?? null}
                />
              ) : null}
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
