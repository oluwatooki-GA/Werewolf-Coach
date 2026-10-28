"use client";

import { useEffect, useRef, useState } from "react";
import type { ReplayLine, ReplayPlayer, ReplayVote } from "@/lib/api";
import {
  BOT_NAME,
  delayFor,
  isHidden,
  speakerOf,
  talks,
  type Playable,
  type Speed,
} from "@/lib/playback";
import { Close, Lock, More, People } from "./Icons";
import { ChatHeader } from "./ChatHeader";
import { Members } from "./Members";
import { Message, type Side } from "./Message";
import { Pill } from "./Pill";
import { Poll } from "./Poll";
import { Playback } from "./Playback";
import { Post } from "./Post";
import { Thoughts } from "./Thoughts";
import { Typing } from "./Typing";
import { WolfChat } from "./WolfChat";
import styles from "./Room.module.css";

/** Which side a bubble sits on: the player you watch as, nobody, or the wolves. */
export type Bubbles = "player" | "left" | "teams";

const BUBBLES: { id: Bubbles; label: string }[] = [
  { id: "player", label: "Watch as a player" },
  { id: "left", label: "Everyone on the left" },
  { id: "teams", label: "Wolves on the right" },
];

const STORE = "werewolf-coach.bubbles";

type Props = {
  entries: Playable[];
  players: ReplayPlayer[];
  /** The chat's name, in the header. */
  title: string;
  /** The line under the name when nobody is typing. Defaults to the players' names. */
  subtitle?: string;
  avatar: React.ReactNode;
  /** A message to select when the page opens, so its private note is already showing. */
  startAt?: string;
  /** Play the game as a live chat, one message at a time. Off shows it all at once. */
  autoplay?: boolean;
  /** The welcome chat: roles stay hidden until the start message arrives, and thoughts open inline. */
  story?: boolean;
  /** A notice at the top of the chat, like a messenger's encryption notice. */
  welcome?: React.ReactNode;
  label: string;
};

type Selectable = ReplayLine | ReplayVote;

export function Room({
  entries,
  players,
  title,
  subtitle,
  avatar,
  startAt,
  autoplay = true,
  story = false,
  welcome,
  label,
}: Props) {
  const feed = useRef<HTMLDivElement>(null);
  const menuBox = useRef<HTMLDivElement>(null);
  const stick = useRef(true); // keep the newest message in view, unless the reader scrolled away
  const total = entries.length;

  const [shown, setShown] = useState(autoplay ? 0 : total);
  const [playing, setPlaying] = useState(autoplay);
  const [speed, setSpeed] = useState<Speed>("normal");
  const [typingAt, setTypingAt] = useState<number | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [roles, setRoles] = useState(true);
  const [moves, setMoves] = useState(false);
  const [bubbles, setBubbles] = useState<Bubbles>("player");
  const [watchAs, setWatchAs] = useState(
    () =>
      players.find((p) => p.role === "Seer")?.name ??
      players.find((p) => p.team === "Village")?.name ??
      players[0]?.name ??
      "",
  );
  const [menu, setMenu] = useState(false);
  const [panel, setPanel] = useState<"message" | "players" | null>(story || !startAt ? null : "message");
  const [selected, setSelected] = useState<string | null>(story ? null : (startAt ?? null));
  const [isolated, setIsolated] = useState<string | null>(null);

  const count = Math.min(shown, total);
  const finished = shown >= total;
  const ids = entries.map((e, i) => (e.kind === "line" ? e.ref : e.kind === "vote" ? `vote-${i}` : ""));
  const startIndex = startAt ? ids.indexOf(startAt) : -1;
  // in the welcome chat the roles appear when the start message arrives, never before
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
  const mode: Bubbles = story ? "left" : bubbles;
  const open = !story && panel !== null;

  const farFromEnd = () => {
    const box = feed.current;
    return box ? box.scrollHeight - box.scrollTop - box.clientHeight : 0;
  };

  // the bubble side the reader chose before comes back after hydration
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORE);
      /* eslint-disable react-hooks/set-state-in-effect -- reads the browser once, after hydration */
      if (saved === "player" || saved === "left" || saved === "teams") setBubbles(saved);
      /* eslint-enable react-hooks/set-state-in-effect */
    } catch {
      // private windows can refuse storage; the default is fine
    }
  }, []);

  function chooseBubbles(next: Bubbles) {
    setBubbles(next);
    try {
      localStorage.setItem(STORE, next);
    } catch {
      // not remembered, still applied
    }
  }

  // a deep link or a reader who asks for less motion gets the whole game at once
  useEffect(() => {
    if (!autoplay || story) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const hash = window.location.hash.slice(1);
    if (!reduce && !hash) return;
    /* eslint-disable react-hooks/set-state-in-effect -- reads the browser once, after hydration */
    setSpeed("instant");
    setShown(total);
    setPlaying(false);
    if (hash && ids.includes(hash)) {
      setSelected(hash);
      setPanel("message");
    }
    /* eslint-enable react-hooks/set-state-in-effect */
    if (hash) requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView?.());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, story, total]);

  // the live chat: wait, show "typing", then post the next message
  useEffect(() => {
    if (!playing || speed === "instant" || shown >= total) return;
    const next = entries[shown];
    if (!next) return;
    // private entries and the "who is listening" lines are not shown, so they take no time
    const hidden =
      isHidden(next, showRoles) || (next.kind === "direction" && next.tone === "listening" && !moves);
    const wait = delayFor(next, speed, hidden);
    const timers: number[] = [];
    if (talks(next) && !hidden && wait > 0) {
      timers.push(
        window.setTimeout(() => {
          stick.current = farFromEnd() < 400;
          setTypingAt(shown);
        }, wait * 0.4),
      );
    }
    timers.push(
      window.setTimeout(() => {
        stick.current = farFromEnd() < 400;
        setShown(shown + 1);
      }, wait),
    );
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [playing, speed, shown, total, entries, showRoles, moves]);

  // follow the newest message while the reader is at the bottom, gliding rather than jumping
  const glide = useRef(0);
  const gliding = useRef(false);
  function follow() {
    const box = feed.current; // its bottom padding is the room left under the newest message
    if (!box) return;
    cancelAnimationFrame(glide.current);
    const from = box.scrollTop;
    const to = box.scrollHeight - box.clientHeight;
    if (to - from < 2) return;
    const start = performance.now();
    gliding.current = true;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 450);
      box.scrollTop = from + (to - from) * (1 - (1 - t) ** 3);
      if (t < 1) {
        glide.current = requestAnimationFrame(step);
      } else {
        gliding.current = false;
        setAtBottom(farFromEnd() < 400);
      }
    };
    glide.current = requestAnimationFrame(step);
  }

  useEffect(() => {
    if (shown === 0 || !stick.current) return;
    follow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, typingAt]);

  // a reader who scrolls takes over from the glide
  useEffect(() => {
    const box = feed.current;
    const stop = () => {
      cancelAnimationFrame(glide.current);
      gliding.current = false;
    };
    box?.addEventListener("wheel", stop, { passive: true });
    box?.addEventListener("touchstart", stop, { passive: true });
    return () => {
      box?.removeEventListener("wheel", stop);
      box?.removeEventListener("touchstart", stop);
    };
  }, []);

  // the options menu closes when you tap anywhere else
  useEffect(() => {
    if (!menu) return;
    const away = (event: PointerEvent) => {
      if (!menuBox.current?.contains(event.target as Node)) setMenu(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [menu]);

  function restart() {
    setShown(0);
    setTypingAt(null);
    setSelected(story ? null : (startAt ?? null));
    setPanel(null);
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

  function seek(to: number) {
    setShown(to);
    setTypingAt(null);
    stick.current = true;
    setSelected(null);
    setPanel(null);
  }

  function select(id: string) {
    setSelected(id);
    if (!story) setPanel("message");
  }

  function dismiss() {
    setSelected(null);
    setPanel(null);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") return dismiss();
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const all = [...(feed.current?.querySelectorAll<HTMLElement>("[data-msg]") ?? [])];
    const next = all[all.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      event.preventDefault();
      next.focus();
      select(next.dataset.id ?? "");
    }
  }

  const nameOf = (e: Playable) => speakerOf(e) ?? "";
  const teamOf = (e: Playable) =>
    e.kind === "line" || e.kind === "vote" ? e.team : e.kind === "wolf_chat" ? "Wolves" : "Village";
  const sideOf = (e: Playable): Side => {
    if (mode === "player") return nameOf(e) === watchAs ? "out" : "in";
    if (mode === "teams" && showRoles) return teamOf(e) === "Wolves" ? "out" : "in";
    return "in";
  };

  // a day's votes are one poll: the first vote of a run draws it, the rest only add to it
  const polls = new Map<number, number[]>();
  let group: number[] | null = null;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i] as Playable;
    if (e.kind !== "vote") {
      group = null;
    } else if (group && entries[i - 1]?.round === e.round) {
      group.push(i);
    } else {
      group = [i];
      polls.set(i, group);
    }
  }

  // what each entry puts on screen, so a run of messages by one player shares a name and a tail
  const visible = entries.slice(0, count);
  const rendered = (e: Playable) =>
    e.kind === "line" ||
    e.kind === "vote" ||
    e.kind === "bot" ||
    (e.kind === "direction" ? !(e.tone === "listening" && !moves) : showRoles);
  const firsts: boolean[] = [];
  let before: string | null = null;
  for (let i = 0; i < visible.length; i++) {
    const e = visible[i] as Playable;
    if (!story && e.round > 0 && visible[i - 1]?.round !== e.round) before = null;
    if (!rendered(e) || e.kind === "vote") {
      firsts.push(false);
      if (e.kind === "vote") before = null;
    } else if (talks(e)) {
      const key = e.kind === "wolf_chat" ? `wolves:${nameOf(e)}` : nameOf(e);
      firsts.push(key !== before);
      before = key;
    } else {
      firsts.push(false);
      before = null;
    }
  }

  const names = subtitle ?? players.map((p) => p.name).join(", ");
  const typist = typing ? speakerOf(typing) : null;
  const voting = typing?.kind === "vote";

  return (
    <div className={styles.room} data-panel={open ? "open" : "closed"}>
      <section className={styles.channel} aria-label={label}>
        <ChatHeader
          avatar={avatar}
          title={title}
          subtitle={typist ? <em>{typist} {voting ? "voting" : "typing"}…</em> : names}
          onInfo={story ? undefined : () => setPanel((p) => (p === "players" ? null : "players"))}
          infoLabel="Players in this chat"
          actions={
            story ? null : (
              <>
                <button
                  type="button"
                  className={styles.icon}
                  aria-label="Players"
                  aria-pressed={panel === "players"}
                  onClick={() => setPanel((p) => (p === "players" ? null : "players"))}
                >
                  <People />
                </button>
                <div className={styles.menu} ref={menuBox}>
                  <button
                    type="button"
                    className={styles.icon}
                    aria-label="Chat options"
                    aria-expanded={menu}
                    onClick={() => setMenu((m) => !m)}
                  >
                    <More />
                  </button>
                  {menu ? (
                    <div className={styles.sheet} role="group" aria-label="Chat options">
                      <fieldset>
                        <legend>Bubbles</legend>
                        {BUBBLES.map((b) => (
                          <label key={b.id}>
                            <input
                              type="radio"
                              name="bubbles"
                              checked={bubbles === b.id}
                              onChange={() => chooseBubbles(b.id)}
                            />
                            <span>{b.label}</span>
                          </label>
                        ))}
                        {bubbles === "player" ? (
                          <label className={styles.pick}>
                            <span>Watching as</span>
                            <select value={watchAs} onChange={(e) => setWatchAs(e.target.value)}>
                              {players.map((p) => (
                                <option key={p.name} value={p.name}>
                                  {p.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                      </fieldset>
                      <fieldset>
                        <legend>Show</legend>
                        <label>
                          <input type="checkbox" checked={roles} onChange={(e) => setRoles(e.target.checked)} />
                          <span>Roles and private notes</span>
                        </label>
                        <label>
                          <input type="checkbox" checked={moves} onChange={(e) => setMoves(e.target.checked)} />
                          <span>Show tactics</span>
                        </label>
                      </fieldset>
                    </div>
                  ) : null}
                </div>
              </>
            )
          }
        />

        <div className={styles.stage}>
          <div
            ref={feed}
            role="feed"
            aria-label={`${label}, messages`}
            className={styles.feed}
            data-live={(autoplay && !finished) || undefined}
            onScroll={() => {
              // the glide moves the feed too, and that is not the reader leaving the bottom
              if (!gliding.current) setAtBottom(farFromEnd() < 400);
            }}
          >
            {welcome ? (
              <Pill as="div" tone="notice">
                {welcome}
              </Pill>
            ) : null}

            {visible.map((e, i) => {
              const divider =
                !story && (i === 0 || visible[i - 1]?.round !== e.round) && e.round > 0 ? (
                  <Pill as="h2" tone="date" id={`round-${e.round}`}>
                    Round {e.round}
                  </Pill>
                ) : null;
              const first = firsts[i] ?? false;
              const id = ids[i] ?? "";
              const fresh = live && i === count - 1;
              const wrap = (node: React.ReactNode) => (
                <div key={i} className={styles.item} data-fresh={fresh || undefined}>
                  {divider}
                  {node}
                </div>
              );

              if (e.kind === "bot") {
                return wrap(
                  <Post name={BOT_NAME} bot first={first}>
                    <p>{e.text}</p>
                  </Post>,
                );
              }
              if (e.kind === "direction") {
                if (!rendered(e)) return divider ? wrap(null) : null;
                return wrap(<Pill tone={e.tone === "end" ? "end" : "system"}>{e.text}</Pill>);
              }
              if (e.kind === "vote") {
                const members = polls.get(i);
                if (!members) return divider ? wrap(null) : null;
                const votes = members.filter((j) => j < count);
                const newest = live && entries[count - 1]?.kind === "vote" ? (ids[count - 1] ?? null) : null;
                return wrap(
                  <Poll
                    round={e.round}
                    ballots={votes.map((j) => ({ id: ids[j] ?? "", vote: entries[j] as ReplayVote }))}
                    expected={members.length}
                    selected={chosen}
                    isolated={isolated}
                    showRoles={showRoles}
                    fresh={newest}
                    onSelect={select}
                    onKeyDown={onKeyDown}
                  />,
                );
              }
              if (e.kind === "line") {
                const side = sideOf(e);
                const speaker = nameOf(e);
                return wrap(
                  <>
                    <Message
                      id={id}
                      entry={e}
                      side={side}
                      first={first}
                      named={!(side === "out" && mode === "player")}
                      showRoles={showRoles}
                      showMoves={moves}
                      selected={id !== "" && id === chosen}
                      dim={isolated !== null && speaker !== isolated}
                      quotes={quotes}
                      onSelect={select}
                      onKeyDown={onKeyDown}
                    />
                    {story && id !== "" && id === chosen ? (
                      <div className={styles.inline}>
                        <Thoughts entry={e} cast={cast} showRoles={showRoles} surface="inline" />
                      </div>
                    ) : null}
                  </>,
                );
              }
              // wolf chat, the night and the Seer's check: only shown with roles, and marked private
              if (!showRoles) return divider ? wrap(null) : null;
              if (e.kind === "wolf_chat") {
                return wrap(
                  <WolfChat
                    speaker={e.speaker}
                    text={e.text}
                    side={sideOf(e)}
                    first={first}
                    named={!(sideOf(e) === "out" && mode === "player")}
                    dim={isolated !== null && isolated !== e.speaker}
                  />,
                );
              }
              return wrap(
                <Pill tone="private">
                  <Lock size={14} />
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
                </Pill>,
              );
            })}
            {typist && !voting ? <Typing name={typist} /> : null}
          </div>

          {!atBottom && playing && !finished ? (
            <button
              type="button"
              className={styles.latest}
              onClick={() => {
                stick.current = true;
                follow();
              }}
            >
              Jump to the latest message
            </button>
          ) : null}
        </div>

        {autoplay ? (
          <footer className={styles.footer}>
            <Playback
              playing={playing}
              finished={finished}
              speed={speed}
              shown={count}
              total={total}
              onToggle={() => setPlaying((p) => !p)}
              onRestart={restart}
              onSpeed={chooseSpeed}
              onSeek={seek}
            />
          </footer>
        ) : null}
      </section>

      {story ? null : (
        <aside className={styles.info} aria-label="Details" hidden={!open}>
          <header className={styles.infohead}>
            <button type="button" className={styles.icon} aria-label="Close" onClick={dismiss}>
              <Close />
            </button>
            <h2>{panel === "players" ? "Players" : "Message info"}</h2>
          </header>
          <div className={styles.infobody}>
            {panel === "players" ? (
              <Members players={players} showRoles={showRoles} isolated={isolated} onIsolate={setIsolated} />
            ) : (
              <Thoughts entry={entry} cast={cast} showRoles={showRoles} surface="panel" />
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
