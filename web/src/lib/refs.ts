/** A line number the agents write in their own words, such as "R2-4": round 2, the fourth line. */
const REF = /\bR\d+-\d+\b/g;

export type Piece = string | { ref: string };

/** Split a message into plain text and the line numbers inside it, in order. */
export function splitRefs(text: string): Piece[] {
  const pieces: Piece[] = [];
  let from = 0;
  for (const match of text.matchAll(REF)) {
    const at = match.index ?? 0;
    if (at > from) pieces.push(text.slice(from, at));
    pieces.push({ ref: match[0] });
    from = at + match[0].length;
  }
  if (from < text.length) pieces.push(text.slice(from));
  return pieces;
}

/** Scroll to a message and flash it, so the reader sees which one was meant. */
export function jumpTo(ref: string): void {
  const row = document.getElementById(ref);
  if (!row) return;
  row.scrollIntoView?.({ block: "center" });
  row.setAttribute("data-flash", "");
  window.setTimeout(() => row.removeAttribute("data-flash"), 1400);
}
