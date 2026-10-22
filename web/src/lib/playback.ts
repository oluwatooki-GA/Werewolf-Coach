import type { ReplayEntry } from "./api";

/** How fast a replay plays. "Instant" shows the whole game at once. */
export type Speed = "slow" | "normal" | "fast" | "instant";

export const SPEEDS: { id: Speed; label: string }[] = [
  { id: "slow", label: "Slow" },
  { id: "normal", label: "Normal" },
  { id: "fast", label: "Fast" },
  { id: "instant", label: "Instant" },
];

/** The pause between one message and the next, before the length of the message is counted. */
const BASE_MS = { slow: 2000, normal: 1000, fast: 500 } as const;

const PRIVATE = new Set(["wolf_chat", "night", "seer_result"]);

/** A line, a vote or wolf chat has a speaker; the morning news and the night do not. */
export function talks(entry: ReplayEntry): boolean {
  return entry.kind === "line" || entry.kind === "vote" || entry.kind === "wolf_chat";
}

export function speakerOf(entry: ReplayEntry): string | null {
  if (entry.kind === "line" || entry.kind === "wolf_chat") return entry.speaker;
  if (entry.kind === "vote") return entry.voter;
  return null;
}

/** With roles off the public view has no wolf chat, no night and no Seer check. */
export function isHidden(entry: ReplayEntry, showRoles: boolean): boolean {
  return !showRoles && PRIVATE.has(entry.kind);
}

/**
 * Milliseconds before this entry appears. A longer message takes a little longer, within a
 * second and a half at normal speed, so the chat has a rhythm. Hidden entries and instant
 * playback do not wait at all.
 */
export function delayFor(entry: ReplayEntry, speed: Speed, hidden: boolean): number {
  if (speed === "instant" || hidden) return 0;
  const base = BASE_MS[speed];
  if (entry.kind === "line") {
    const length = Math.min(Math.max(0.8 + entry.text.length / 300, 0.8), 1.5);
    return Math.round(base * length);
  }
  if (entry.kind === "vote" || entry.kind === "wolf_chat") return Math.round(base * 0.9);
  return Math.round(base * 0.4);
}
