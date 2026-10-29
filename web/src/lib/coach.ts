import type { Generation } from "./api";
import { cardParts } from "./format";

export type CardNode = {
  id: string;
  name: string;
  version: string;
  /** The champion's own line runs along the top; challengers that lost hang below it. */
  row: "champion" | "challenger";
  /** One column per generation, and the starting champion in column 0. */
  col: number;
  status: "start" | "champion" | "rejected" | "invalid";
  /** The generation that produced it, which the node links to. */
  gen: number | null;
  /** How it did against the champion on the same seeds. */
  won: number | null;
  games: number | null;
};

export type CardEdge = {
  from: string;
  to: string;
  /** Promoted: the challenger became the champion. Otherwise it was tried and dropped. */
  promoted: boolean;
};

/**
 * The family tree of the coach's cards. Each generation the coach writes one challenger from the
 * current champion and tests it on the same seeds. A challenger that wins replaces the champion
 * (it joins the top row); one that does not hangs below it, linked to the card it came from.
 */
export function lineage(generations: Generation[]): { nodes: CardNode[]; edges: CardEdge[] } {
  const first = generations[0];
  if (!first) return { nodes: [], edges: [] };

  const nodes: CardNode[] = [];
  const edges: CardEdge[] = [];
  const parts = (ref: string) => {
    const { name, version } = cardParts(ref);
    return { name, version };
  };

  let champion: CardNode = {
    id: `start:${first.champion_before}`,
    ...parts(first.champion_before),
    row: "champion",
    col: 0,
    status: "start",
    gen: null,
    won: first.champion_arm?.wins ?? null,
    games: first.champion_arm?.games ?? null,
  };
  nodes.push(champion);

  for (const gen of generations) {
    if (!gen.challenger_card) {
      // the coach wrote cards but none passed the checks, so nothing was tested
      const stub: CardNode = {
        id: `g${gen.number}:none`,
        name: "No valid card",
        version: "",
        row: "challenger",
        col: gen.number,
        status: "invalid",
        gen: gen.number,
        won: null,
        games: null,
      };
      nodes.push(stub);
      edges.push({ from: champion.id, to: stub.id, promoted: false });
      continue;
    }
    const arm = gen.challenger_arm;
    const challenger: CardNode = {
      id: `g${gen.number}:${gen.challenger_card}`,
      ...parts(gen.challenger_card),
      row: gen.promote ? "champion" : "challenger",
      col: gen.number,
      status: gen.promote ? "champion" : "rejected",
      gen: gen.number,
      won: arm?.wins ?? null,
      games: arm?.games ?? null,
    };
    nodes.push(challenger);
    edges.push({ from: champion.id, to: challenger.id, promoted: gen.promote });
    if (gen.promote) champion = challenger;
  }
  return { nodes, edges };
}
