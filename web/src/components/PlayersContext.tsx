"use client";

import { createContext, useContext } from "react";
import { avatarColor, roleColor } from "@/lib/people";

export type Team = "Village" | "Wolves";

type Value = {
  players: ReadonlyMap<string, { role: string; team: Team }>;
  /** Roles are shown, so a player is drawn in their role's colour and team icon. */
  show: boolean;
};

const Players = createContext<Value>({ players: new Map(), show: false });

export const PlayersProvider = Players.Provider;

/**
 * How to draw a player. Once roles are shown, a wolf is the wolf colour and a Seer the Seer colour
 * wherever they appear, with their team's icon. Until then everyone gets a colour of their own,
 * which says nothing about the role. A bot, or anyone not in the game, keeps its own colour.
 */
export function usePlayer(name: string): { team: Team | null; color: string } {
  const { players, show } = useContext(Players);
  const known = show ? players.get(name) : undefined;
  return known ? { team: known.team, color: roleColor(known.role) } : { team: null, color: avatarColor(name) };
}
