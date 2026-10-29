"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Card, PlayStatus } from "@/lib/api";
import { cardParts, plural } from "@/lib/format";
import { roleColor } from "@/lib/people";
import { DEFAULT, cardsFor, noPicks, readGame, refOf, SIDES, startGame, type Picks, type SideId } from "@/lib/play";
import { ChatAvatar } from "./ChatAvatar";
import { ChatPage } from "./ChatPage";
import { Pill } from "./Pill";
import { Embed, Post } from "./Post";
import { Typing } from "./Typing";
import styles from "./PlayBoard.module.css";

type Phase =
  | { name: "pick"; message?: string }
  | { name: "starting" }
  | { name: "playing"; id: string }
  | { name: "finished"; gameId: string }
  | { name: "stopped"; reason: string };

const POLL_MS = 2000;

/**
 * The play chat. The visitor picks one strategy card for each side (or the default instructions),
 * starts a game, and when the agents have finished it opens as a replay. The browser only talks to
 * the site's own /api/play routes.
 */
export function PlayBoard({ cards, status }: { cards: Card[]; status: PlayStatus }) {
  const [picks, setPicks] = useState<Picks>(noPicks);
  const [phase, setPhase] = useState<Phase>({ name: "pick" });
  const byRef = new Map(cards.map((card) => [refOf(card), card]));
  const playing = phase.name === "playing" ? phase.id : null;
  const asking = useRef(false);

  // while a game is being played, ask how it is going until it is over
  useEffect(() => {
    if (!playing) return;
    let timer: number | undefined;
    let cancelled = false;
    const poll = async () => {
      if (asking.current) return;
      asking.current = true;
      const state = await readGame(playing);
      asking.current = false;
      if (cancelled) return;
      if (state?.status === "finished" && state.game_id) {
        setPhase({ name: "finished", gameId: state.game_id });
      } else if (state?.status === "stopped") {
        setPhase({ name: "stopped", reason: state.reason ?? "The game stopped." });
      } else {
        timer = window.setTimeout(poll, POLL_MS);
      }
    };
    timer = window.setTimeout(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [playing]);

  async function start() {
    setPhase({ name: "starting" });
    const started = await startGame(picks);
    setPhase(started.ok ? { name: "playing", id: started.id } : { name: "pick", message: started.message });
  }

  const busy = phase.name !== "pick";
  const left = status.games_left;

  return (
    <ChatPage
      avatar={<ChatAvatar kind="play" size={40} />}
      title="Play"
      subtitle="Pick the cards, then watch the agents play"
    >
      <Post name="Lab" bot>
        <p>
          Pick a strategy card for each side. The agents play one game with your choices, and when it ends you can read it
          like any other game. A card tells a player how to play; Default means the standard instructions for that role.
        </p>
      </Post>

      {SIDES.map((side) => {
        const options = cardsFor(cards, side.role);
        const chosen = byRef.get(picks[side.id]);
        return (
          <section key={side.id} className={styles.side} aria-labelledby={`side-${side.id}`}>
            <Pill as="h2" tone="date" id={`side-${side.id}`}>
              <span style={{ color: roleColor(side.role) }}>{side.label}</span>
            </Pill>
            <div className={styles.choice} role="radiogroup" aria-label={side.label}>
              <Tile
                label="Default"
                summary="No strategy card: the agents use the standard instructions for this role."
                checked={picks[side.id] === DEFAULT}
                disabled={busy}
                onPick={() => setPicks((now) => ({ ...now, [side.id]: DEFAULT }))}
              />
              {options.map((card) => (
                <Tile
                  key={refOf(card)}
                  label={cardParts(card.id).name}
                  summary={card.summary}
                  checked={picks[side.id] === refOf(card)}
                  disabled={busy}
                  onPick={() => setPicks((now) => ({ ...now, [side.id as SideId]: refOf(card) }))}
                />
              ))}
            </div>
            {chosen ? (
              <Post name="Lab" bot first={false}>
                <Embed title={`What the card says`}>
                  <p>{chosen.instructions}</p>
                  <p className={styles.source}>{chosen.source}</p>
                </Embed>
              </Post>
            ) : null}
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
      {phase.name === "playing" ? (
        <>
          <Post name="Lab" bot>
            <p>The agents are playing. This usually takes a minute or two. You can leave this page open.</p>
          </Post>
          <Typing name="Lab" />
        </>
      ) : null}
      {phase.name === "finished" ? (
        <Post name="Lab" bot>
          <p>Your game is ready.</p>
          <Link href={`/games/${phase.gameId}`} className={styles.watch}>
            Watch the game
          </Link>
        </Post>
      ) : null}
      {phase.name === "stopped" ? (
        <Post name="Lab" bot>
          <p>{phase.reason}</p>
          <button type="button" className={styles.start} onClick={() => setPhase({ name: "pick" })}>
            Try again
          </button>
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
