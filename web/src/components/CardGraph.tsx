import type { Generation } from "@/lib/api";
import { lineage, type CardNode } from "@/lib/coach";
import { ENOUGH_GAMES } from "@/lib/format";
import styles from "./CardGraph.module.css";

const W = 176; // a card
const H = 78;
const GAP = 56;
const PAD = 12;
const ROW = { champion: PAD, challenger: PAD + H + 44 } as const;

const x = (col: number) => PAD + col * (W + GAP);

/** What a card is, in words, so the picture never depends on colour. */
function role(node: CardNode): string {
  switch (node.status) {
    case "start":
      return "Starting champion";
    case "champion":
      return "New champion";
    case "rejected":
      return "Not better, dropped";
    default:
      return "Failed the checks";
  }
}

function result(node: CardNode): string | null {
  if (node.won === null || node.games === null) return null;
  return `Won ${node.won} of ${node.games} ${node.games === 1 ? "game" : "games"}`;
}

/** A line from the right of one card to the left of the next, curved when they are on different rows. */
function edgePath(from: CardNode, to: CardNode): string {
  const x1 = x(from.col) + W;
  const y1 = ROW[from.row] + H / 2;
  const x2 = x(to.col);
  const y2 = ROW[to.row] + H / 2;
  const mid = (x1 + x2) / 2;
  return `M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${x2 - 6} ${y2}`;
}

type Props = {
  generations: Generation[];
  /** A card was picked. */
  onPick: (node: CardNode) => void;
  /** The node whose details are open. */
  picked: string | null;
};

/**
 * The coach's cards as a family tree. The champion's line runs along the top; each generation the
 * coach writes one challenger and tests it against the champion, and a winner joins the top line
 * while a loser hangs below it. Each card says what it is in words. Tapping one opens its details.
 */
export function CardGraph({ generations, onPick, picked }: Props) {
  const { nodes, edges } = lineage(generations);
  if (nodes.length === 0) return null;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const cols = Math.max(...nodes.map((n) => n.col)) + 1;
  const hasLower = nodes.some((n) => n.row === "challenger");
  const width = PAD * 2 + cols * W + (cols - 1) * GAP;
  const height = PAD * 2 + H + (hasLower ? 44 + H : 0);
  const summary = nodes
    .map((n) => [n.name, n.version ? `version ${n.version}` : null, role(n), result(n)].filter(Boolean).join(", "))
    .join(". ");

  return (
    <figure className={styles.figure}>
      <div className={styles.scroll}>
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-label={`The cards, as a family tree. ${summary}.`} role="group" focusable="false">
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0 8 4 0 8Z" className={styles.arrow} />
            </marker>
          </defs>

          {edges.map((edge) => {
            const from = byId.get(edge.from);
            const to = byId.get(edge.to);
            if (!from || !to) return null;
            return (
              <path
                key={`${edge.from}>${edge.to}`}
                d={edgePath(from, to)}
                className={styles.edge}
                data-promoted={edge.promoted || undefined}
                markerEnd="url(#arrow)"
              />
            );
          })}

          {nodes.map((node) => {
            const played = result(node);
            const thin = node.games !== null && node.games < ENOUGH_GAMES;
            return (
              <g
                key={node.id}
                className={styles.node}
                data-status={node.status}
                data-picked={picked === node.id || undefined}
                transform={`translate(${x(node.col)} ${ROW[node.row]})`}
                role="button"
                tabIndex={0}
                aria-label={`${node.name}${node.version ? `, version ${node.version}` : ""}. ${role(node)}.${played ? ` ${played}.` : ""} Tap for details.`}
                aria-pressed={picked === node.id}
                onClick={() => onPick(node)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onPick(node);
                  }
                }}
              >
                <rect width={W} height={H} rx="12" />
                <text x="12" y="25" className={styles.name}>
                  {node.name.length > 21 ? `${node.name.slice(0, 20)}…` : node.name}
                </text>
                <text x="12" y="44" className={styles.role}>
                  {node.version ? `v${node.version}, ` : ""}
                  {role(node)}
                </text>
                {played ? (
                  <text x="12" y="63" className={styles.result}>
                    {played}
                    {thin ? ", not clear yet" : ""}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}
