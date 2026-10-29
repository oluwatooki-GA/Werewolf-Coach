import type { Card, PlayState } from "./api";

/** The four things a visitor picks a card for, and the role each card must be for. */
export const SIDES = [
  { id: "wolf", label: "Wolves", role: "Werewolf", ask: "the wolves play" },
  { id: "villager", label: "Villagers", role: "Villager", ask: "the villagers play" },
  { id: "seer", label: "Seer", role: "Seer", ask: "the Seer plays" },
  { id: "doctor", label: "Doctor", role: "Doctor", ask: "the Doctor plays" },
] as const;

export type SideId = (typeof SIDES)[number]["id"];
export type Picks = Record<SideId, string>; // a card as "id@version", or "default"

export const DEFAULT = "default";
export const noPicks = (): Picks => ({ wolf: DEFAULT, villager: DEFAULT, seer: DEFAULT, doctor: DEFAULT });
export const refOf = (card: Card) => `${card.id}@${card.version}`;

/** Only cards for the role are offered, so a wrong card can never be picked. */
export const cardsFor = (cards: Card[], role: string) => cards.filter((card) => card.role === role);

export type Started = { ok: true; id: string } | { ok: false; message: string };

/** Ask the site (which asks the API) to start a game with these cards. */
export async function startGame(picks: Picks): Promise<Started> {
  try {
    const response = await fetch("/api/play", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(picks),
    });
    const body = (await response.json().catch(() => ({}))) as { id?: string; detail?: unknown };
    if (response.ok && body.id) return { ok: true, id: body.id };
    const detail = typeof body.detail === "string" ? body.detail : "The game could not be started.";
    return { ok: false, message: detail };
  } catch {
    return { ok: false, message: "The site could not reach the game server. Try again in a moment." };
  }
}

export async function readGame(id: string): Promise<PlayState | null> {
  try {
    const response = await fetch(`/api/play/${id}`);
    return response.ok ? ((await response.json()) as PlayState) : null;
  } catch {
    return null;
  }
}
