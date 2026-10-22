import { describe, expect, it } from "vitest";
import type { Replay } from "./api";
import fixture from "../test/replay.fixture.json";
import { excerpt, storyCaption } from "./replay";

const replay = fixture as unknown as Replay;

describe("excerpt", () => {
  it("starts just before the focus line and runs a few entries after it", () => {
    const part = excerpt(replay.entries, "R1-1");
    expect(part[0]?.kind).toBe("direction"); // the morning news
    expect(part.some((e) => e.kind === "line" && e.ref === "R1-1")).toBe(true);
    expect(part.length).toBe(6);
  });

  it("falls back to the start of the game when the line is missing", () => {
    expect(excerpt(replay.entries, "R9-9")[0]).toBe(replay.entries[0]);
  });
});

describe("storyCaption", () => {
  const part = excerpt(replay.entries, "R1-1");

  it("starts by setting the scene, without giving the roles away", () => {
    const text = storyCaption(part, "R1-1", 0, part.length);
    expect(text).toMatch(/Eight AI players/);
    expect(text).not.toMatch(/Hal/);
  });

  it("names the liar and what it did once the featured line arrives", () => {
    const at = part.findIndex((e) => e.kind === "line" && e.ref === "R1-1");
    expect(storyCaption(part, "R1-1", at + 1, part.length)).toBe(
      "Hal is a wolf. It just claimed to be the Seer, which was a lie. On the right is what it was thinking when it sent that message.",
    );
  });

  it("ends by pointing at what to do next", () => {
    expect(storyCaption(part, "R1-1", part.length, part.length)).toMatch(/watch the whole game/);
  });
});
