import { describe, expect, it } from "vitest";
import type { Replay } from "./api";
import fixture from "../test/replay.fixture.json";
import { blocks, excerpt, momentHeadline } from "./replay";

const replay = fixture as unknown as Replay;

describe("blocks", () => {
  it("joins the run of private entries before the first line into one block", () => {
    const first = blocks(replay.entries)[0];
    expect(first?.kind).toBe("private");
    expect(first && "entries" in first ? first.entries.map((e) => e.kind) : []).toEqual([
      "wolf_chat",
      "wolf_chat",
      "seer_result",
      "night",
    ]);
  });

  it("keeps public entries, in order, as they are", () => {
    const rest = blocks(replay.entries).slice(1).map((b) => b.kind);
    expect(rest.slice(0, 3)).toEqual(["direction", "line", "direction"]);
  });
});

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

describe("momentHeadline", () => {
  it("says who lied and what they claimed, from the line itself", () => {
    expect(momentHeadline(replay.entries, "R1-1")).toBe(
      "A wolf claims to be the Seer. Its private note says why.",
    );
  });

  it("falls back to a plain sentence when the line is missing", () => {
    expect(momentHeadline(replay.entries, "R9-9")).toMatch(/^Eight AI agents play Werewolf/);
  });
});
