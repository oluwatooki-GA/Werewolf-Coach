import type { ReplayEntry } from "./api";

const PRIVATE_KINDS = new Set(["wolf_chat", "night", "seer_result"]);

/** An entry, or a run of private entries (wolf chat, the night) shown together on the facing page. */
export type Block = ReplayEntry | { kind: "private"; round: number; entries: ReplayEntry[] };

/** Consecutive private entries become one block, so the night is one note, not four empty rows. */
export function blocks(entries: ReplayEntry[]): Block[] {
  const out: Block[] = [];
  for (const entry of entries) {
    const last = out[out.length - 1];
    if (!PRIVATE_KINDS.has(entry.kind)) {
      out.push(entry);
    } else if (last && last.kind === "private") {
      last.entries.push(entry);
    } else {
      out.push({ kind: "private", round: entry.round, entries: [entry] });
    }
  }
  return out;
}

/**
 * A few entries around one line, for the home page: the setup before it (the wolves' plan, the
 * morning) and the replies after it. Falls back to the start of the game if the line is missing.
 */
export function excerpt(entries: ReplayEntry[], focus: string, before = 1, after = 4): ReplayEntry[] {
  const at = entries.findIndex((e) => e.kind === "line" && e.ref === focus);
  const index = at === -1 ? 0 : at;
  return entries.slice(Math.max(0, index - before), index + after + 1);
}

/** What the home page says about the featured moment, from the line itself, never hard-coded. */
export function momentHeadline(entries: ReplayEntry[], focus: string): string {
  const line = entries.find((e) => e.kind === "line" && e.ref === focus);
  if (!line || line.kind !== "line") return "Eight AI agents play Werewolf. Here is one of their games.";
  const who = line.role === "Werewolf" ? "wolf" : line.role.toLowerCase();
  const claim = line.claim?.role;
  const act = claim ? `claims to be the ${claim}` : "lies";
  return `A ${who} ${act}. Its private note says why.`;
}
