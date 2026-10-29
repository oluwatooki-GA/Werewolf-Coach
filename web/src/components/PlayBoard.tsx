"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Card, PlayStatus, PlayTable, ReplayEntry, ReplayPlayer } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";
import { roleColor } from "@/lib/people";
import { DEFAULT, cardsFor, dealTable, noPicks, readLive, refOf, SIDES, startGame, type Picks } from "@/lib/play";
import { ChatAvatar } from "./ChatAvatar";
import { ChatPage } from "./ChatPage";
import { Pill } from "./Pill";
import { Post } from "./Post";
import { Room } from "./Room";
import styles from "./PlayBoard.module.css";

type Phase =
  | { name: "pick"; message?: string }
  | { name: "starting" }
  | { name: "playing"; id: string }
  | { name: "finished"; gameId: string }
  | { name: "stopped"; reason: string }
  | { name: "lost" };

const POLL_MS = 1000;
const MAX_FAILURES = 5; // failed looks in a row before the page stops asking

/**
 * The play chat. The visitor sees a table of eight players, picks a strategy card for each one (or
 * the default instructions) and starts a game. The game then plays out on the page as the agents
 * play it, in the same chat a replay uses, and ends with a link to the finished replay. The
 * browser only talks to the site's own /api/play routes.
 */
export function PlayBoard({ cards, status, table: dealt }: { cards: Card[]; status: PlayStatus; table: PlayTable }) {
  const [table, setTable] = useState(dealt);
  const [picks, setPicks] = useState<Picks>(() => noPicks(dealt));
  const [phase, setPhase] = useState<Phase>({ name: "pick" });
  const [notice, setNotice] = useState("");
  const byRef = new Map(cards.map((card) => [refOf(card), card]));
  const playing = phase.name === "playing" ? phase.id : null;
  const [entries, setEntries] = useState<ReplayEntry[]>([]);
  const got = useRef(0); // how many entries of this game the page has

  // while a game is being played, ask for what is new once a second until it is over
  useEffect(() => {
    if (!playing) return;
    let timer: number | undefined;
    let cancelled = false;
    let failures = 0;
    const poll = async () => {
      const after = got.current;
      const live = await readLive(playing, after);
      if (cancelled) return;
      if (!live) {
        failures += 1;
        if (failures >= MAX_FAILURES) setPhase({ name: "lost" });
        else timer = window.setTimeout(poll, POLL_MS);
        return;
      }
      failures = 0;
      if (live.entries.length > 0) {
        got.current = after + live.entries.length;
        setEntries((now) => (now.length === after ? [...now, ...live.entries] : now));
      }
      if (live.status === "finished" && live.game_id) {
        setPhase({ name: "finished", gameId: live.game_id });
      } else if (live.status === "stopped") {
        setPhase({ name: "stopped", reason: live.reason ?? "The game stopped." });
      } else {
        timer = window.setTimeout(poll, POLL_MS);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [playing]);

  async function start() {
    got.current = 0;
    setEntries([]);
    setPhase({ name: "starting" });
    const started = await startGame(table.seed, picks);
    setPhase(started.ok ? { name: "playing", id: started.id } : { name: "pick", message: started.message });
  }

  // new seats mean new roles, so the old choices no longer fit and start again from Default
  async function shuffle() {
    const next = await dealTable();
    if (!next) {
      setNotice("The site could not deal new seats. Try again in a moment.");
      return;
    }
    setNotice("");
    setTable(next);
    setPicks(noPicks(next));
  }

  const setCards = (names: string[], ref: string) =>
    setPicks((now) => ({ ...now, ...Object.fromEntries(names.map((name) => [name, ref])) }));

  const busy = phase.name !== "pick" && phase.name !== "stopped" && phase.name !== "lost";
  const left = status.games_left;

  if (phase.name === "playing" || phase.name === "finished" || phase.name === "stopped" || phase.name === "lost") {
    const cast: ReplayPlayer[] = table.seats.map((seat) => ({
      name: seat.name,
      role: seat.role,
      team: seat.role === "Werewolf" ? "Wolves" : "Village",
      card: picks[seat.name] && picks[seat.name] !== DEFAULT ? (picks[seat.name] ?? null) : null,
    }));
    return (
      <Room
        entries={entries}
        players={cast}
        title="Play"
        subtitle="Your game"
        avatar={<ChatAvatar kind="play" size={40} />}
        label="Your game"
        cards={Object.fromEntries(byRef)}
        growing={phase.name === "playing"}
        after={
          phase.name === "finished" ? (
            <>
              <p>Your game is ready.</p>
              <Link href={`/games/${phase.gameId}`} className={styles.watch}>
                Watch the full replay
              </Link>
            </>
          ) : phase.name === "stopped" || phase.name === "lost" ? (
            <>
              <p>
                {phase.name === "stopped"
                  ? phase.reason
                  : "The site lost the connection to the game. The game carries on without it, and will be in the games list when it ends."}
              </p>
              <button type="button" className={styles.start} onClick={() => setPhase({ name: "pick" })}>
                {phase.name === "stopped" ? "Try again" : "Back to the cards"}
              </button>
            </>
          ) : null
        }
      />
    );
  }

  return (
    <ChatPage
      avatar={<ChatAvatar kind="play" size={40} />}
      title="Play"
      subtitle="Pick the cards, then watch the agents play"
    >
      <Post name="Lab" bot>
        <p>
          Pick a strategy card for each player. The agents play one game with your choices, and when it ends you can read it
          like any other game. A card tells a player how to play; Default means the standard instructions for that role.
          Seats and roles are dealt at random.
        </p>
        <button type="button" className={styles.shuffle} disabled={busy} onClick={shuffle}>
          Shuffle seats
        </button>
        {notice ? <p role="alert">{notice}</p> : null}
      </Post>

      {SIDES.map((side) => {
        const players = table.seats.filter((seat) => seat.role === side.role);
        if (players.length === 0) return null;
        const options = cardsFor(cards, side.role);
        const names = players.map((seat) => seat.name);
        return (
          <section key={side.role} className={styles.side} aria-labelledby={`side-${side.role}`}>
            <Pill as="h2" tone="date" id={`side-${side.role}`}>
              <span style={{ color: roleColor(side.role) }}>{side.label}</span>
            </Pill>
            {players.length > 1 ? (
              <select
                className={styles.all}
                aria-label={`Same card for all ${side.label}`}
                value=""
                disabled={busy}
                onChange={(event) => event.target.value && setCards(names, event.target.value)}
              >
                <option value="">Same card for all {side.label}…</option>
                <option value={DEFAULT}>Default</option>
                {options.map((card) => (
                  <option key={refOf(card)} value={refOf(card)}>
                    {cardParts(card.id).name}
                  </option>
                ))}
              </select>
            ) : null}
            {players.map((seat) => {
              const chosen = byRef.get(picks[seat.name] ?? DEFAULT);
              return (
                <div key={seat.name} className={styles.player}>
                  <p className={styles.who}>
                    <b>{seat.name}</b>
                    <span style={{ color: roleColor(seat.role) }}>{seat.role}</span>
                  </p>
                  <div className={styles.choice} role="radiogroup" aria-label={seat.name}>
                    <Tile
                      label="Default"
                      summary="No strategy card: the agents use the standard instructions for this role."
                      checked={picks[seat.name] === DEFAULT}
                      disabled={busy}
                      onPick={() => setCards([seat.name], DEFAULT)}
                    />
                    {options.map((card) => (
                      <Tile
                        key={refOf(card)}
                        label={cardParts(card.id).name}
                        summary={card.summary}
                        checked={picks[seat.name] === refOf(card)}
                        disabled={busy}
                        onPick={() => setCards([seat.name], refOf(card))}
                      />
                    ))}
                  </div>
                  <details className={styles.says}>
                    <summary>What the card says</summary>
                    <p>{chosen ? chosen.instructions : table.default_card}</p>
                    <p className={styles.source}>
                      {chosen ? chosen.source : "The default: what every player is told when no card is chosen."}
                    </p>
                  </details>
                </div>
              );
            })}
          </section>
        );
      })}

      {!status.available ? (
        <Pill as="div" tone="notice">
          <p>{status.reason}</p>
        </Pill>
      ) : left != null ? (
        <Pill tone="system">
          {left === 0 ? "No games left today." : `${plural(left, "game")} left today.`}
        </Pill>
      ) : null}

      {phase.name === "pick" ? (
        <div className={styles.actions}>
          {phase.message ? <p role="alert" className={styles.message}>{phase.message}</p> : null}
          <button type="button" className={styles.start} disabled={!status.available} onClick={start}>
            Start the game
          </button>
        </div>
      ) : null}

      {phase.name === "starting" ? (
        <Post name="Lab" bot>
          <p>Starting your game…</p>
        </Post>
      ) : null}
    </ChatPage>
  );
}

function Tile(props: { label: string; summary: string; checked: boolean; disabled: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={props.checked}
      aria-label={props.label}
      disabled={props.disabled}
      className={styles.tile}
      onClick={props.onPick}
    >
      <b>{props.label}</b>
      <span>{props.summary}</span>
    </button>
  );
}
