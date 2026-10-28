import type { Card, ReplayPlayer } from "@/lib/api";
import { cardParts } from "@/lib/format";
import { Avatar } from "./Avatar";
import { RoleTag } from "./RoleTag";
import styles from "./PlayerCard.module.css";

type Props = {
  player: ReplayPlayer;
  /** The strategy card this player was given, if the site has its text. */
  card: Card | null;
  /** Every card, so "built on" can name the card this one grew from. */
  cards: Record<string, Card>;
  showRoles: boolean;
  /** How they left the game, if they have by this point in the replay. */
  out?: string;
  following: boolean;
  onFollow: () => void;
};

/** One player: who they are, and the strategy card that told them how to play. */
export function PlayerCard({ player, card, cards, showRoles, out, following, onFollow }: Props) {
  const parent = card?.parent ? cards[card.parent] : null;
  return (
    <section className={styles.box} aria-label={`${player.name}, strategy`}>
      <header className={styles.head}>
        <Avatar name={player.name} size={56} out={Boolean(out)} />
        <div>
          <h3>{player.name}</h3>
          {showRoles ? <RoleTag role={player.role} team={player.team} /> : <p className={styles.hint}>Role hidden</p>}
          {out ? <p className={styles.out}>{out}</p> : null}
        </div>
      </header>

      {!showRoles ? (
        <p className={styles.hint}>
          Roles and strategy cards are hidden. Turn on roles and private notes in the chat options (⋮) to see them.
        </p>
      ) : card ? (
        <>
          <h4>Strategy card</h4>
          <p className={styles.name}>
            <b>{cardParts(card.id).name}</b>, version {card.version}
          </p>
          {card.summary ? <p className={styles.summary}>{card.summary}</p> : null}
          <p className={styles.script}>{card.instructions}</p>
          <p className={styles.source}>
            {parent ? `Built on ${cardParts(parent.id).name}, version ${parent.version}. ` : ""}
            {card.source}
          </p>
        </>
      ) : player.card ? (
        <>
          <h4>Strategy card</h4>
          <p className={styles.name}>
            <b>{cardParts(player.card).name}</b>, version {cardParts(player.card).version}
          </p>
          <p className={styles.hint}>The text of this card is not on the site.</p>
        </>
      ) : (
        <>
          <h4>Strategy card</h4>
          <p className={styles.hint}>No strategy card. {player.name} played with the default instructions for its role.</p>
        </>
      )}

      <button type="button" className={styles.follow} aria-pressed={following} onClick={onFollow}>
        {following ? "Show everyone again" : `Show only ${player.name}'s messages`}
      </button>
    </section>
  );
}
