import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { featured } from "./featured";

const { api, apiOrNull } = vi.hoisted(() => ({ api: vi.fn(), apiOrNull: vi.fn() }));
vi.mock("./api", async (original) => ({ ...(await original<typeof import("./api")>()), api, apiOrNull }));

import { loadGame } from "./game-source";

const chosen = featured.games[0]?.id ?? "";

beforeEach(() => {
  api.mockReset();
  apiOrNull.mockReset();
});

describe("loadGame", () => {
  it("reads the game and the cards from the API when it answers", async () => {
    apiOrNull.mockResolvedValue({ id: "7-live", entries: [] });
    api.mockResolvedValue([{ id: "wolf.x", version: "1" }]);
    const loaded = await loadGame("7-live");
    expect(loaded).toEqual({ replay: { id: "7-live", entries: [] }, cards: [{ id: "wolf.x", version: "1" }] });
  });

  it("says a game that is not there is not there", async () => {
    apiOrNull.mockResolvedValue(null);
    expect(await loadGame("7-gone")).toBeNull();
  });

  it("opens a hand-picked game from the site's own copy while the API is asleep", async () => {
    apiOrNull.mockRejectedValue(new ApiError(0, "The API is not answering."));
    const loaded = await loadGame(chosen);
    expect(loaded).not.toBeNull();
    expect(loaded).not.toBe("waking");
    expect((loaded as { replay: { id: string } }).replay.id).toBe(chosen);
  });

  it("says the API is waking for any other game, and does not throw", async () => {
    apiOrNull.mockRejectedValue(new ApiError(0, "The API is not answering."));
    expect(await loadGame("7-live")).toBe("waking");
  });

  it("treats a server error from a waking service the same way", async () => {
    apiOrNull.mockRejectedValue(new ApiError(503, "The API answered 503."));
    expect(await loadGame("7-live")).toBe("waking");
  });

  it("does not hide a real problem", async () => {
    apiOrNull.mockRejectedValue(new Error("a bug"));
    await expect(loadGame("7-live")).rejects.toThrow("a bug");
  });
});
