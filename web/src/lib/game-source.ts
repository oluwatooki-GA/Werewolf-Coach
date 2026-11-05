import { api, apiOrNull, isAsleep } from "./api";
import type { Card, Replay } from "./api";
import { bundledReplay, featured } from "./featured";

export type LoadedGame = { replay: Replay; cards: Card[] };

/**
 * A game and the cards for it. From the API when it answers; from the site's own copy for a
 * hand-picked game when it does not; "waking" for any other game, since the API is asleep and
 * will answer in a minute. null means the game does not exist.
 */
export async function loadGame(id: string): Promise<LoadedGame | "waking" | null> {
  try {
    const replay = await apiOrNull<Replay>(`/games/${id}/replay`);
    if (!replay) return null;
    return { replay, cards: await api<Card[]>("/strategies") };
  } catch (error) {
    if (!isAsleep(error)) throw error; // anything but a sleeping API is a real problem
    const replay = await bundledReplay(id);
    return replay ? { replay, cards: featured.cards } : "waking";
  }
}
