import { describe, expect, it } from "vitest";
import ids from "../data/featured-ids.json";
import { bundledReplay, featured } from "./featured";

describe("the hand-picked games", () => {
  it("are the 15 that were chosen, each once", () => {
    expect(featured.games.map((g) => g.id)).toEqual(ids);
    expect(new Set(ids).size).toBe(15);
  });

  it("include both winners, so the list is not one-sided", () => {
    const winners = new Set(featured.games.map((g) => g.winner));
    expect(winners).toEqual(new Set(["Wolves", "Village"]));
  });

  it("include the game the welcome chat plays, and the cards to read", () => {
    expect(ids).toContain(featured.welcome.game_id);
    expect(featured.cards.length).toBeGreaterThan(0);
  });

  it("each open without the API, as a whole replay", async () => {
    for (const id of ids) {
      const replay = await bundledReplay(id);
      expect(replay?.id).toBe(id);
      expect(replay?.entries.length).toBeGreaterThan(0);
    }
  });

  it("do not include a game that was not chosen, or anything that is not a game id", async () => {
    expect(await bundledReplay("999-deadbeef")).toBeNull();
    expect(await bundledReplay("../featured-ids")).toBeNull();
    expect(await bundledReplay("")).toBeNull();
  });
});
