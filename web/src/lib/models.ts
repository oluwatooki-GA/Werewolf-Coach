import type { GameSummary } from "./api";

/**
 * A rough tier by name, best first: Opus, Fable, Sonnet, GPT-4.1, Haiku, GPT-4.1 mini, nano, then
 * anything unknown, then scripted test agents (no model). It is an ordering for the list, not a
 * benchmark, and ties keep the order the API gave (newest first).
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

/** Games with the strongest models first. The sort is stable, so newest stays first within a model. */
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
