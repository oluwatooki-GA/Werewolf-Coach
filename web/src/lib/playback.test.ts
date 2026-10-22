import { describe, expect, it } from "vitest";
import type { Replay, ReplayEntry } from "./api";
import fixture from "../test/replay.fixture.json";
import { delayFor, isHidden, speakerOf, talks } from "./playback";

const entries = (fixture as unknown as Replay).entries;
const line = entries.find((e) => e.kind === "line") as ReplayEntry;
const direction = entries.find((e) => e.kind === "direction") as ReplayEntry;
const wolfChat = entries.find((e) => e.kind === "wolf_chat") as ReplayEntry;

describe("delayFor", () => {
  it("waits about a second between messages at normal speed", () => {
    const ms = delayFor(line, "normal", false);
    expect(ms).toBeGreaterThanOrEqual(800);
    expect(ms).toBeLessThanOrEqual(1600);
  });

  it("waits about half a second when fast and about two when slow", () => {
    expect(delayFor(line, "fast", false)).toBeLessThan(delayFor(line, "normal", false));
    expect(delayFor(line, "slow", false)).toBeGreaterThan(delayFor(line, "normal", false));
    expect(delayFor(line, "fast", false)).toBeGreaterThanOrEqual(400);
    expect(delayFor(line, "slow", false)).toBeLessThanOrEqual(3200);
  });

  it("gives a longer message a little longer, never unbounded", () => {
    const long = { ...line, text: "word ".repeat(200) } as ReplayEntry;
    const short = { ...line, text: "Hi." } as ReplayEntry;
    expect(delayFor(long, "normal", false)).toBeGreaterThan(delayFor(short, "normal", false));
    expect(delayFor(long, "normal", false)).toBeLessThanOrEqual(1500);
  });

  it("moves quickly over system lines and not at all over hidden or instant ones", () => {
    expect(delayFor(direction, "normal", false)).toBeLessThan(delayFor(line, "normal", false));
    expect(delayFor(wolfChat, "normal", true)).toBe(0);
    expect(delayFor(line, "instant", false)).toBe(0);
  });
});

describe("who is talking", () => {
  it("says a line, a vote and wolf chat are messages and a stage direction is not", () => {
    expect(talks(line)).toBe(true);
    expect(talks(wolfChat)).toBe(true);
    expect(talks(direction)).toBe(false);
  });

  it("names the speaker for the typing indicator", () => {
    expect(speakerOf(line)).toBe("Hal");
    expect(speakerOf(wolfChat)).toBe("Fay");
    expect(speakerOf(direction)).toBeNull();
  });

  it("hides private entries while roles are off, and nothing else", () => {
    expect(isHidden(wolfChat, false)).toBe(true);
    expect(isHidden(wolfChat, true)).toBe(false);
    expect(isHidden(line, false)).toBe(false);
    expect(isHidden(direction, false)).toBe(false);
  });
});
