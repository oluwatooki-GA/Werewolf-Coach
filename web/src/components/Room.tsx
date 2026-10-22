"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import type { ReplayEntry, ReplayLine, ReplayPlayer, ReplayVote } from "@/lib/api";
import { delayFor, isHidden, speakerOf, talks, type Speed } from "@/lib/playback";
import { storyCaption } from "@/lib/replay";
import { Avatar } from "./Avatar";
import { Members } from "./Members";
import { Message } from "./Message";
import { Playback } from "./Playback";
import { TeamMark } from "./TeamMark";
import { Thoughts } from "./Thoughts";
import { Typing } from "./Typing";
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
  /** Play the game as a live chat, one message at a time. Off shows it all at once. */
  autoplay?: boolean;
  /** The home page's guided demo: roles stay hidden until the start message arrives. */
  story?: boolean;
  /** An introduction shown above the feed, like a channel's welcome message. */
  welcome?: React.ReactNode;
  label: string;
};

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

type Selectable = ReplayLine | ReplayVote;

export function Room({
  entries,
  players,
  title,
  topic,
  startAt,
  compact = false,
  autoplay = true,
  story = false,
  welcome,
  label,
}: Props) {
  const feed = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const stick = useRef(true); // keep the newest message in view, unless the reader scrolled away
  const total = entries.length;

  const [shown, setShown] = useState(autoplay ? 0 : total);
  const [playing, setPlaying] = useState(autoplay);
  const [speed, setSpeed] = useState<Speed>("normal");
  const [typingAt, setTypingAt] = useState<number | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [roles, setRoles] = useState(true);
  const [moves, setMoves] = useState(!compact);
  const [selected, setSelected] = useState<string | null>(story ? null : (startAt ?? null));
  const [isolated, setIsolated] = useState<string | null>(null);

  const count = Math.min(shown, total);
  const finished = shown >= total;
  const ids = entries.map((e, i) => (e.kind === "line" ? e.ref : e.kind === "vote" ? `vote-${i}` : ""));
  const startIndex = startAt ? ids.indexOf(startAt) : -1;
  // in the guided demo the roles appear when the start message arrives, never before
  const revealed = !story || (startIndex >= 0 && count > startIndex);
  const showRoles = story ? revealed : roles;
  const chosen = selected ?? (story && revealed ? (startAt ?? null) : null);
  const index = ids.indexOf(chosen ?? "\0");
  const entry = index >= 0 ? (entries[index] as Selectable) : null;
  const typing = playing && !finished && typingAt === shown ? entries[shown] : undefined;
  const cast = new Map(players.map((p) => [p.name, p]));
  const quotes = new Map(
    entries.flatMap((e) => (e.kind === "line" ? [[e.ref, e] as [string, ReplayLine]] : [])),
  );
  const live = autoplay && speed !== "instant";

  const nearBottom = () =>
    (end.current?.getBoundingClientRect().top ?? 0) < window.innerHeight + 200;

  // a deep link or a reader who asks for less motion gets the whole game at once
  useEffect(() => {
    if (!autoplay) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const hash = window.location.hash.slice(1);
    if (!reduce && (compact || !hash)) return;
    /* eslint-disable react-hooks/set-state-in-effect -- reads the browser once, after hydration */
    setSpeed("instant");
    setShown(total);
    setPlaying(false);
    if (hash && ids.includes(hash)) setSelected(hash);
    /* eslint-enable react-hooks/set-state-in-effect */
    if (hash) requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView?.());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, compact, total]);

  // the live chat: wait, show "is typing", then post the next message
  useEffect(() => {
    if (!playing || speed === "instant" || shown >= total) return;
    const next = entries[shown];
    if (!next) return;
    const hidden = isHidden(next, showRoles);
    const wait = delayFor(next, speed, hidden);
    const timers: number[] = [];
    if (talks(next) && !hidden && wait > 0) {
      timers.push(
        window.setTimeout(() => {
          stick.current = nearBottom();
          setTypingAt(shown);
        }, wait * 0.4),
      );
    }
    timers.push(
      window.setTimeout(() => {
        stick.current = nearBottom();
        setShown(shown + 1);
      }, wait),
    );
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [playing, speed, shown, total, entries, showRoles]);

  // follow the newest message while the reader is at the bottom
  useEffect(() => {
    if (compact || shown === 0 || !stick.current) return;
    end.current?.scrollIntoView?.({ block: "end" });
  }, [shown, typingAt, compact]);

  useEffect(() => {
    const target = end.current;
    if (compact || !target || typeof IntersectionObserver === "undefined") return;
    const watcher = new IntersectionObserver(([seen]) => setAtBottom(seen?.isIntersecting ?? true), {
      rootMargin: "0px 0px 200px 0px",
    });
    watcher.observe(target);
    return () => watcher.disconnect();
  }, [compact]);

  function restart() {
    setShown(0);
    setTypingAt(null);
    setSelected(story ? null : (startAt ?? null));
    if (speed === "instant") setSpeed("normal");
    stick.current = true;
    setPlaying(true);
  }

  function chooseSpeed(next: Speed) {
    setSpeed(next);
    if (next === "instant") {
      setShown(total);
      setPlaying(false);
    } else if (!finished) {
      setPlaying(true);
    }
  }

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
  const rounds = [...new Set(entries.map((e) => e.round))].filter((r) => r > 0);

  return (
    <div className={styles.room}>
      <section className={styles.channel} aria-label={label}>
        {title ? (
          <header className={styles.bar}>
            <h1>
              <span aria-hidden="true">#</span> {title}
            </h1>
            {topic ? <p className={styles.topic} title={topic}>
                {topic}
              </p> : null}
            {autoplay ? (
              <Playback
                playing={playing}
                finished={finished}
                speed={speed}
                shown={count}
                total={total}
                onToggle={() => setPlaying((p) => !p)}
                onRestart={restart}
                onSpeed={chooseSpeed}
              />
            ) : null}
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

        {welcome ? <div className={styles.welcome}>{welcome}</div> : null}

        {story ? (
          <div className={styles.caption} aria-live="polite">
            <p>{storyCaption(entries, startAt ?? "", count, total)}</p>
            {finished ? (
              <button type="button" onClick={restart}>
                Watch again
              </button>
            ) : null}
          </div>
        ) : null}

        <div ref={feed} role="feed" aria-label={`${label}, messages`} className={styles.feed}>
          {entries.slice(0, count).map((e, i) => {
            const first = i === 0 || entries[i - 1]?.round !== e.round;
            const divider =
              !compact && first && e.round > 0 ? (
                <h2 className={styles.divider} id={`round-${e.round}`}>
                  <span>Round {e.round}</span>
                </h2>
              ) : null;
            const id = ids[i] ?? "";
            const isSelected = id !== "" && id === chosen;
            const fresh = live && i === count - 1;

            if (e.kind === "direction") {
              return (
                <div key={i} className={styles.item} data-fresh={fresh || undefined}>
                  {divider}
                  <p className={styles.system} data-tone={e.tone}>
                    {e.text}
                  </p>
                </div>
              );
            }
            if (e.kind === "line" || e.kind === "vote") {
              return (
                <div key={i} className={styles.item} data-fresh={fresh || undefined}>
                  {divider}
                  <Message
                    id={id}
                    entry={e}
                    showRoles={showRoles}
                    showMoves={moves}
                    quiet={compact}
                    selected={isSelected}
                    dim={isolated !== null && speaker(e) !== isolated}
                    quotes={quotes}
                    onSelect={setSelected}
                    onKeyDown={onKeyDown}
                  />
                  {isSelected ? (
                    <div className={styles.inline}>
                      <Thoughts entry={e} cast={cast} showRoles={showRoles} surface="inline" />
                    </div>
                  ) : null}
                </div>
              );
            }
            // wolf chat, the night and the Seer's check: only shown with roles, and marked private
            if (!showRoles) return <Fragment key={i}>{divider}</Fragment>;
            return (
              <div key={i} className={styles.item} data-fresh={fresh || undefined}>
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
              </div>
            );
          })}
          {typing && speakerOf(typing) ? <Typing name={speakerOf(typing) ?? ""} /> : null}
          <div ref={end} className={styles.end} />
        </div>

        {!compact && !atBottom && playing && !finished ? (
          <button
            type="button"
            className={styles.latest}
            onClick={() => {
              stick.current = true;
              end.current?.scrollIntoView?.({ block: "end" });
            }}
          >
            Jump to the latest message
          </button>
        ) : null}

        {!compact && finished && rounds.length > 0 ? (
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
        <Thoughts entry={entry} cast={cast} showRoles={showRoles} surface="panel" />
        {compact ? null : (
          <Members players={players} showRoles={showRoles} isolated={isolated} onIsolate={setIsolated} />
        )}
      </aside>
    </div>
  );
}
