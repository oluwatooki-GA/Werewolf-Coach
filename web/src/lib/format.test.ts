import { describe, expect, it } from "vitest";
import {
  cardParts,
  ENOUGH_GAMES,
  gel,
  lineNumber,
  moveName,
  percent,
  plural,
  sentence,
  sentences,
  wilson,
} from "./format";

describe("wilson", () => {
  it("matches the interval the API computes", () => {
    // Python: wilson(4, 6) -> (0.2999..., 0.9032...)
    const [low, high] = wilson(4, 6);
    expect(low).toBeCloseTo(0.3, 2);
    expect(high).toBeCloseTo(0.903, 2);
  });

  it("is empty for no games and stays inside 0 and 1", () => {
    expect(wilson(0, 0)).toEqual([0, 0]);
    const [low, high] = wilson(1, 1);
    expect(low).toBeGreaterThan(0);
    expect(high).toBe(1);
  });
});

describe("small helpers", () => {
  it("formats a rate as a whole percent", () => {
    expect(percent(0.6667)).toBe("67%");
    expect(percent(0)).toBe("0%");
  });

  it("pulls a readable name and version out of a card ref", () => {
    expect(cardParts("wolf.fake_seer@2")).toEqual({
      id: "wolf.fake_seer",
      version: "2",
      name: "fake seer",
    });
  });

  it("reads a line number the way the game counts", () => {
    expect(lineNumber("R2-4")).toEqual([2, 4]);
    expect(lineNumber("R10-1")).toEqual([10, 1]);
  });

  it("says moves in words, pluralises and capitalises", () => {
    expect(moveName("accuse_reasoned")).toBe("accuse reasoned");
    expect(plural(1, "game")).toBe("1 game");
    expect(plural(3, "game")).toBe("3 games");
    expect(sentence("no better: x")).toBe("No better: x");
  });

  it("gives each game a gel colour from its id, and the same id the same colour", () => {
    expect(gel("1-845496ae")).toBe(gel("1-845496ae"));
    expect(gel("1-845496ae")).toMatch(/^var\(--gel-[0-5]\)$/);
    const colours = new Set(["1-845496ae", "1-4b12e8cb", "2-33f4107d", "3-65394cd9", "4-6be00ff8"].map(gel));
    expect(colours.size).toBeGreaterThan(2); // games with one seed are still told apart
  });

  it("treats fewer than ten games as too few to compare", () => {
    expect(ENOUGH_GAMES).toBe(10);
  });
});

describe("sentences", () => {
  it("splits the way the coach does, so cuts line up with the card", () => {
    const text = "Take the lead.  Bid 2 or 3 on most turns!\nNever mention the wolf chat.";
    expect(sentences(text)).toEqual([
      "Take the lead.",
      "Bid 2 or 3 on most turns!",
      "Never mention the wolf chat.",
    ]);
  });
});
