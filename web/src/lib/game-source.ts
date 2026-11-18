import { api, apiOrNull, isAsleep } from "./api";
import type { Card, Replay } from "./api";
import { bundledReplay, featured } from "./featured";

export type LoadedGame = { replay: Replay; cards: Card[] };

/**
 * A game and the cards for it. A hand-picked game comes from the site's own copy at once: it needs
 * no wait for a sleeping API, and some of them (games visitors played) are not in the live database.
 * Any other game comes from the API, or is "waking" when the API is asleep and will answer in a
 * minute. null means the game does not exist.
 */
export async function loadGame(id: string): Promise<LoadedGame | "waking" | null> {
  const saved = await bundledReplay(id);
  if (saved) return { replay: saved, cards: featured.cards };
  try {
    const replay = await apiOrNull<Replay>(`/games/${id}/replay`);
    if (!replay) return null;
    return { replay, cards: await api<Card[]>("/strategies") };
  } catch (error) {
    if (!isAsleep(error)) throw error; // anything but a sleeping API is a real problem
    return "waking";
  }
}
