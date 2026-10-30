import type { components } from "./api-types";

type Schemas = components["schemas"];

export type Replay = Schemas["Replay"];
export type ReplayEntry = Replay["entries"][number];
export type ReplayLine = Extract<ReplayEntry, { kind: "line" }>;
export type ReplayVote = Extract<ReplayEntry, { kind: "vote" }>;
export type ReplayPlayer = Schemas["ReplayPlayer"];
export type Subtext = Schemas["Subtext"];
export type GameSummary = Schemas["GameSummary"];
export type GameList = Schemas["GameList"];
export type CardResult = Schemas["CardResult"];
export type Card = Schemas["Card"];
export type Generation = Schemas["Generation"];
export type CoachHistory = Schemas["CoachHistory"];
export type Featured = Schemas["Featured"];
export type PlayStatus = Schemas["PlayStatus"];
export type PlayState = Schemas["PlayState"];
export type PlayTable = Schemas["PlayTable"];
export type PlayLive = Schemas["PlayLive"];
export type AdminOverview = Schemas["AdminOverview"];

/** The API answered, but not with what we asked for. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const apiBase = () => process.env.API_URL ?? "http://localhost:8000";
const base = apiBase;

/** Fetch from the API on the server. The site never calls it from the browser. */
export async function api<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base()}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError(0, "The API is not answering.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, `The API answered ${response.status} for ${path}.`);
  }
  return (await response.json()) as T;
}

/** Like `api`, but a 404 becomes null so a page can call notFound(). */
export async function apiOrNull<T>(path: string): Promise<T | null> {
  try {
    return await api<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
