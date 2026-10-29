import { describe, expect, it } from "vitest";
import type { Generation } from "./api";
import { lineage } from "./coach";

const arm = (card: string, wins: number, games: number) => ({ card, seeds: [1], wins, games, clean: true, cost: "0", stopped: null });

function gen(
  number: number,
  before: string,
  challenger: string | null,
  promote: boolean,
  results: [number, number] = [1, 1],
): Generation {
  return {
    side: "wolf",
    number,
    champion_before: before,
    champion_after: promote && challenger ? challenger : before,
    challenger_card: challenger,
    promote,
    champion_arm: challenger ? arm(before, 1, 1) : null,
    challenger_arm: challenger ? arm(challenger, results[0], results[1]) : null,
    decision: promote ? "better" : "no better",
  } as unknown as Generation;
}

describe("lineage", () => {
  it("is empty when the coach has not run", () => {
    expect(lineage([])).toEqual({ nodes: [], edges: [] });
  });

  it("starts with the champion in column 0 and hangs a losing challenger below it", () => {
    const { nodes, edges } = lineage([gen(1, "wolf.accuse_early@2", "wolf.calm@1", false)]);
    expect(nodes.map((n) => [n.name, n.row, n.col, n.status])).toEqual([
      ["accuse early", "champion", 0, "start"],
      ["calm", "challenger", 1, "rejected"],
    ]);
    expect(edges).toEqual([{ from: nodes[0]?.id, to: nodes[1]?.id, promoted: false }]);
  });

  it("branches every challenger from the same champion while none wins", () => {
    const { nodes, edges } = lineage([
      gen(1, "wolf.a@1", "wolf.b@1", false),
      gen(2, "wolf.a@1", "wolf.c@1", false),
    ]);
    expect(edges.map((e) => e.from)).toEqual([nodes[0]?.id, nodes[0]?.id]);
    expect(nodes.filter((n) => n.row === "challenger")).toHaveLength(2);
  });

  it("moves a promoted challenger onto the champion's row and branches the next one from it", () => {
    const { nodes, edges } = lineage([
      gen(1, "wolf.a@1", "wolf.b@1", true),
      gen(2, "wolf.b@1", "wolf.c@1", false),
    ]);
    const b = nodes.find((n) => n.name === "b");
    expect(b).toMatchObject({ row: "champion", status: "champion", col: 1 });
    expect(edges[0]).toMatchObject({ promoted: true });
    expect(edges[1]?.from).toBe(b?.id);
  });

  it("keeps how each card did, and which generation made it", () => {
    const { nodes } = lineage([gen(1, "wolf.a@1", "wolf.b@1", false, [3, 8])]);
    expect(nodes[1]).toMatchObject({ won: 3, games: 8, gen: 1 });
    expect(nodes[0]).toMatchObject({ won: 1, games: 1, gen: null });
  });

  it("shows a generation whose cards all failed the checks as a stub, not a card", () => {
    const { nodes, edges } = lineage([gen(1, "wolf.a@1", null, false)]);
    expect(nodes[1]).toMatchObject({ name: "No valid card", status: "invalid" });
    expect(edges[0]?.promoted).toBe(false);
  });
});
