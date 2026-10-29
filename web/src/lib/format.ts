/** Small, pure helpers the pages share. Tested in format.test.ts. */

/** 0.6667 -> "67%". */
export function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

/** The 95% Wilson interval for k wins out of n games: the same formula the API uses. */
export function wilson(k: number, n: number, z = 1.96): [number, number] {
  if (n === 0) return [0, 0];
  const p = k / n;
  const centre = (p + (z * z) / (2 * n)) / (1 + (z * z) / n);
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / (1 + (z * z) / n);
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}

/** Below this many games two cards cannot be told apart (DESIGN 6.1). */
export const ENOUGH_GAMES = 10;

/** "wolf.fake_seer@2" -> { id: "wolf.fake_seer", version: "2", name: "fake seer" }. */
export function cardParts(ref: string): { id: string; version: string; name: string } {
  const [id = ref, version = ""] = ref.split("@");
  const name = (id.split(".")[1] ?? id).replaceAll("_", " ");
  return { id, version, name };
}

/** A move name for reading: "accuse_reasoned" -> "accuse reasoned". */
export function moveName(move: string): string {
  return move.replaceAll("_", " ");
}

/** What the lab calls a finding, in words a newcomer can read. */
export function markName(label: string): string {
  const names: Record<string, string> = {
    lie: "Lie",
    fake_claim: "Fake role claim",
    counter_claim: "Counter-claim",
    bus: "Betrayed a partner",
    shield: "Protected a partner",
    hit: "Named a real wolf",
  };
  return names[label] ?? sentence(moveName(label));
}

/** "R2-4" -> [2, 4], so lines sort and compare as the game numbers them. */
export function lineNumber(ref: string): [number, number] {
  const [round = "0", n = "0"] = ref.replace("R", "").split("-");
  return [Number(round), Number(n)];
}

/** The rule sets the games were played under. */
export function ruleLabel(version: string): string {
  if (version === "v3") return "v3 rules: 4 tokens a day, 10 turns, wolves talk up to 5 messages a night, an abstention counts against a removal";
  return version === "v2" ? "v2 rules: 4 tokens a day, 10 turns" : "v1 rules: 3 tokens a day, 8 turns";
}

/** One lighting-gel colour per game (from its id), so tabs are told apart at a glance. */
export function gel(key: number | string): string {
  const text = String(key);
  // FNV-1a with a final mix, so ids that differ only in a few characters still spread out
  let hash = 2166136261;
  for (const char of text) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 15), 2246822519) >>> 0;
  hash ^= hash >>> 13;
  return `var(--gel-${(hash >>> 0) % 6})`;
}

/** The same sentence split the coach uses, so a card shows what it kept and cut. */
export function sentences(text: string): string[] {
  return text
    .replace(/\s+/g, " ")
    .trim()
    .split(/(?<=[.!?])\s+/)
    .filter(Boolean);
}

/** Capitalise the first letter: "no better: ..." -> "No better: ...". */
export function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** "lie low wolves, track votes villagers" from the cards a game's seats played. */
export function matchupOf(cards: Record<string, string>): string {
  const refs = [...new Set(Object.values(cards))];
  const name = (prefix: string) => {
    const ref = refs.find((r) => r.startsWith(prefix));
    return ref ? cardParts(ref).name : null;
  };
  const wolves = name("wolf.");
  const village = name("villager.");
  if (!wolves && !village) return "Default strategies";
  return `${wolves ?? "default"} wolves, ${village ?? "default"} villagers`;
}
