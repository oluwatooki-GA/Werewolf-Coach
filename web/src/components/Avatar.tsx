"use client";

import { initial } from "@/lib/people";
import { usePlayer } from "./PlayersContext";
import styles from "./Avatar.module.css";

/** A wolf's head: two ears, a broad face, eyes and a nose cut out of the shape. */
function WolfHead() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M2.5 1.5 9 6h6l6.5-4.5-1.2 10.2c-.3 3-1.8 5.3-4.3 7.1L12 22.5l-4-3.7c-2.5-1.8-4-4.1-4.3-7.1L2.5 1.5Zm5.6 9.2 2.9 1.2-.5 1.7-3.1-.8Zm7.8 0-2.9 1.2.5 1.7 3.1-.8ZM10.5 16.6h3L12 18.4Z"
      />
    </svg>
  );
}

/** A villager: a head and shoulders. */
function VillagerBust() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="8" r="4.2" fill="currentColor" />
      <path d="M3.5 21c0-4.5 3.8-7.2 8.5-7.2s8.5 2.7 8.5 7.2Z" fill="currentColor" />
    </svg>
  );
}

/**
 * A round avatar. With roles shown a wolf wears a wolf's head and a villager a head and
 * shoulders; otherwise it wears the player's initial. The name is always written beside it.
 */
export function Avatar({ name, size = 40, out = false }: { name: string; size?: number; out?: boolean }) {
  const { team, color } = usePlayer(name);
  return (
    <span
      className={styles.avatar}
      data-out={out || undefined}
      data-team={team ?? undefined}
      style={{ background: color, width: size, height: size, fontSize: size * 0.45 }}
      aria-hidden="true"
    >
      {team === "Wolves" ? <WolfHead /> : team === "Village" ? <VillagerBust /> : initial(name)}
    </span>
  );
}
