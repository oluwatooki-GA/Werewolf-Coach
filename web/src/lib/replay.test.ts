import { describe, expect, it } from "vitest";
import type { Replay } from "./api";
import fixture from "../test/replay.fixture.json";
import { departures, excerpt, welcomeNotes } from "./replay";

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

describe("welcomeNotes", () => {
  it("sets the scene without naming anyone", () => {
    const { before } = welcomeNotes(replay.entries, "R1-1");
    expect(before.join(" ")).toMatch(/eight AI agents/);
    expect(before.join(" ")).not.toMatch(/Hal/);
  });

  it("names the liar and what it claimed, from the line itself", () => {
    expect(welcomeNotes(replay.entries, "R1-1").after[0]).toBe(
      "Hal is a wolf. It claimed to be the Seer, which was a lie. Tap the bubble to read what Hal was thinking when it sent it.",
    );
  });

  it("falls back to a plain tap hint when the line is missing", () => {
    expect(welcomeNotes(replay.entries, "R9-9").after[0]).toMatch(/^Tap any message/);
  });
});

describe("departures", () => {
  const names = replay.players.map((p) => p.name);

  it("says who is out and how, from the game's own morning lines", () => {
    expect(departures(replay.entries, replay.entries.length, names).get("Eve")).toBe("Killed in the night, round 1");
  });

  it("gives nothing away before the line has been shown", () => {
    const at = replay.entries.findIndex((e) => e.kind === "direction" && /Eve was killed/.test(e.text));
    expect(departures(replay.entries, at, names).size).toBe(0);
    expect(departures(replay.entries, at + 1, names).has("Eve")).toBe(true);
  });

  it("reads a vote's removal too, and ignores names that are not players", () => {
    const votes = [
      { kind: "direction", round: 2, text: "Cy was removed by the vote." },
      { kind: "direction", round: 3, text: "Zed was removed by the vote." },
    ];
    expect([...departures(votes, 2, names)]).toEqual([["Cy", "Voted out, round 2"]]);
  });
});
