import type { Card, PlayLive, PlayTable } from "./api";

/** The sides a table is grouped into, in the order they are shown; `role` is what the API calls it. */
export const SIDES = [
  { label: "Wolves", role: "Werewolf" },
  { label: "Villagers", role: "Villager" },
  { label: "Seer", role: "Seer" },
  { label: "Doctor", role: "Doctor" },
] as const;

export type Picks = Record<string, string>; // player name -> a card as "id@version", or "default"

export const DEFAULT = "default";
export const noPicks = (table: PlayTable): Picks => Object.fromEntries(table.seats.map((s) => [s.name, DEFAULT]));
export const refOf = (card: Card) => `${card.id}@${card.version}`;

/** Only cards for the role are offered, so a wrong card can never be picked. */
export const cardsFor = (cards: Card[], role: string) => cards.filter((card) => card.role === role);

export type Started = { ok: true; id: string } | { ok: false; message: string };

/** Ask the site (which asks the API) to start a game on this table with these cards. */
export async function startGame(seed: number, picks: Picks): Promise<Started> {
  try {
    const response = await fetch("/api/play", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ seed, cards: picks }),
    });
    const body = (await response.json().catch(() => ({}))) as { id?: string; detail?: unknown };
    if (response.ok && body.id) return { ok: true, id: body.id };
    const detail = typeof body.detail === "string" ? body.detail : "The game could not be started.";
    return { ok: false, message: detail };
  } catch {
    return { ok: false, message: "The site could not reach the game server. Try again in a moment." };
  }
}

/** A newly dealt table, or null if the server could not be reached. */
export async function dealTable(): Promise<PlayTable | null> {
  try {
    const response = await fetch("/api/play/table");
    return response.ok ? ((await response.json()) as PlayTable) : null;
  } catch {
    return null;
  }
}

/** A game being played, from entry `after` on; null if it could not be read. */
export async function readLive(id: string, after: number): Promise<PlayLive | null> {
  try {
    const response = await fetch(`/api/play/${id}/live?after=${after}`);
    if (!response.ok) return null;
    const live = (await response.json()) as PlayLive;
    return Array.isArray(live.entries) ? live : null;
  } catch {
    return null;
  }
}
