"use client";

import type { ReplayLine } from "@/lib/api";
import { jumpTo, splitRefs } from "@/lib/refs";
import styles from "./RefText.module.css";

/**
 * A message with its line numbers made readable. "R2-4" means nothing to a newcomer, so it
 * becomes "Eve's message": a button that scrolls to that bubble and flashes it. A number that
 * matches no line is called "an earlier message" rather than left as a code.
 */
export function RefText({ text, quotes }: { text: string; quotes: ReadonlyMap<string, ReplayLine> }) {
  return (
    <>
      {splitRefs(text).map((piece, i) => {
        if (typeof piece === "string") return piece;
        const line = quotes.get(piece.ref);
        if (!line) return <span key={i}>an earlier message</span>;
        return (
          <button
            key={i}
            type="button"
            className={styles.ref}
            aria-label={`${line.speaker}'s message in round ${line.round}: ${line.text}`}
            title={`${line.speaker}, round ${line.round}: ${line.text}`}
            onClick={(event) => {
              event.stopPropagation();
              jumpTo(piece.ref);
            }}
          >
            {line.speaker}&apos;s message
          </button>
        );
      })}
    </>
  );
}
