import { describe, expect, it } from "vitest";
import type { GameSummary } from "./api";
import { byModel, modelLabel, modelRank, modelsIn } from "./models";

const game = (id: string, model: string) => ({ id, model }) as GameSummary;

describe("modelRank", () => {
  it("puts stronger models first", () => {
    const order = ["claude-opus-5-5", "claude-sonnet-5-5", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", ""];
    const ranks = order.map(modelRank);
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks);
    expect(new Set(ranks).size).toBe(order.length);
  });
});

describe("modelLabel", () => {
  it("writes a model the way a person would", () => {
    expect(modelLabel("claude-sonnet-5-5")).toBe("Claude Sonnet 5.5");
    expect(modelLabel("gpt-4.1-nano")).toBe("GPT-4.1 nano");
    expect(modelLabel("gpt-4.1")).toBe("GPT-4.1");
    expect(modelLabel("")).toBe("Scripted test agents");
    expect(modelLabel("mystery-1")).toBe("mystery-1");
  });
});

describe("byModel and modelsIn", () => {
  const games = [game("a", "gpt-4.1-nano"), game("b", "gpt-4.1-nano"), game("c", "claude-sonnet-5-5"), game("d", "gpt-4.1")];

  it("lists the best model's games first and keeps the order within a model", () => {
    expect(byModel(games).map((g) => g.id)).toEqual(["c", "d", "a", "b"]);
  });

  it("counts the games per model, best model first", () => {
    expect(modelsIn(games)).toEqual([
      { model: "claude-sonnet-5-5", games: 1 },
      { model: "gpt-4.1", games: 1 },
      { model: "gpt-4.1-nano", games: 2 },
    ]);
  });
});
