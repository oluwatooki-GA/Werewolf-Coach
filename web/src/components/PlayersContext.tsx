"use client";

import { createContext, useContext } from "react";

export type Team = "Village" | "Wolves";

type Value = {
  teams: ReadonlyMap<string, Team>;
  /** Roles are shown, so an avatar may wear its team's icon instead of an initial. */
  show: boolean;
};

const Players = createContext<Value>({ teams: new Map(), show: false });

export const PlayersProvider = Players.Provider;

/** The team to draw on a player's avatar: nothing until roles are shown, and nothing for a bot. */
export function useTeam(name: string): Team | null {
  const { teams, show } = useContext(Players);
  return show ? (teams.get(name) ?? null) : null;
}
