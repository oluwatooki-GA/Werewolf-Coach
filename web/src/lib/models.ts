import type { GameSummary } from "./api";

/**
 * A rough tier by name, best first: Opus, Fable, Sonnet, GPT-4.1, Haiku, GPT-4.1 mini, nano, then
 * anything unknown, then scripted test agents (no model). It is an ordering for the list, not a
 * benchmark, and ties keep the order the API gave (by seed: games have no date).
 */
export function modelRank(model: string): number {
  if (!model) return 9;
  const name = model.toLowerCase();
  if (name.includes("opus")) return 0;
  if (name.includes("fable")) return 1;
  if (name.includes("sonnet")) return 2;
  if (name.includes("nano")) return 6;
  if (name.includes("mini")) return 5;
  if (name.includes("haiku")) return 4;
  if (name.startsWith("gpt-4.1")) return 3;
  return 7;
}

const cap = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

/** "claude-sonnet-5-5" -> "Claude Sonnet 5.5", "gpt-4.1-nano" -> "GPT-4.1 nano". */
export function modelLabel(model: string): string {
  if (!model) return "Scripted test agents";
  const claude = model.match(/^claude-([a-z]+)-(\d+)-(\d+)$/i);
  if (claude) return `Claude ${cap(claude[1] ?? "")} ${claude[2]}.${claude[3]}`;
  const gpt = model.match(/^gpt-([\d.]+)(?:-(.+))?$/i);
  if (gpt) return `GPT-${gpt[1]}${gpt[2] ? ` ${gpt[2]}` : ""}`;
  return model;
}

/** Games with the strongest models first. The sort is stable, so the API's order holds within a model. */
export function byModel(games: GameSummary[]): GameSummary[] {
  return [...games].sort((a, b) => modelRank(a.model) - modelRank(b.model));
}

/** Each model that played, best first, with how many games it played. */
export function modelsIn(games: GameSummary[]): { model: string; games: number }[] {
  const counts = new Map<string, number>();
  for (const game of games) counts.set(game.model, (counts.get(game.model) ?? 0) + 1);
  return [...counts]
    .map(([model, count]) => ({ model, games: count }))
    .sort((a, b) => modelRank(a.model) - modelRank(b.model));
}

export type SortId = "model" | "site" | "most" | "fewest";

/** The ways the list of games can be ordered. */
export const SORTS: { id: SortId; label: string }[] = [
  { id: "model", label: "Strongest model" },
  { id: "site", label: "Played here first" },
  { id: "most", label: "Most rounds" },
  { id: "fewest", label: "Fewest rounds" },
];

/** Every sort starts from strongest model first, so games that tie keep that order. */
export function sortGames(games: GameSummary[], sort: SortId): GameSummary[] {
  const ranked = byModel(games);
  if (sort === "site") return ranked.sort((a, b) => Number(b.source === "play") - Number(a.source === "play"));
  if (sort === "most") return ranked.sort((a, b) => b.rounds - a.rounds);
  if (sort === "fewest") return ranked.sort((a, b) => a.rounds - b.rounds);
  return ranked;
}
