import type { Card, Featured, GameSummary, Replay } from "./api";
import saved from "../data/featured/games.json";

/**
 * Fifteen hand-picked games, the strategy cards and the welcome moment, saved in the site itself
 * (`npm run featured` refreshes them from a running API). They show while the API is asleep.
 */
export const featured = saved as unknown as { games: GameSummary[]; welcome: Featured; cards: Card[] };

const CHOSEN = new Set(featured.games.map((g) => g.id));

/** A hand-picked game's whole replay from the site's own copy, or null for any other id. */
export async function bundledReplay(id: string): Promise<Replay | null> {
  if (!CHOSEN.has(id)) return null; // also keeps anything but a chosen id out of the import below
  return (await import(`../data/featured/replays/${id}.json`)).default as Replay;
}
