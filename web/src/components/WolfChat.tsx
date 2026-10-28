import { avatarColor } from "@/lib/people";
import { Avatar } from "./Avatar";
import { Lock } from "./Icons";
import type { Side } from "./Message";
import styles from "./Message.module.css";

type Props = {
  speaker: string;
  text: string;
  side: Side;
  first: boolean;
  named: boolean;
  dim: boolean;
  onPlayer: (name: string) => void;
};

/** A message in the wolves' private chat: an outlined bubble that says only the wolves saw it. */
export function WolfChat({ speaker, text, side, first, named, dim, onPlayer }: Props) {
  return (
    <article className={styles.row} data-side={side} data-first={first || undefined} data-dim={dim || undefined} data-static>
      {side === "in" ? (
        <span className={styles.gutter}>
          {first ? (
            <button type="button" className={styles.person} aria-label={`${speaker}: show their card`} onClick={() => onPlayer(speaker)}>
              <Avatar name={speaker} size={32} />
            </button>
          ) : null}
        </span>
      ) : null}
      <div className={styles.bubble} data-private>
        {first ? (
          <header className={styles.head}>
            {named ? (
              <button
                type="button"
                className={styles.name}
                style={{ color: side === "in" ? avatarColor(speaker) : undefined }}
                onClick={() => onPlayer(speaker)}
              >
                {speaker}
              </button>
            ) : null}
            <span className={styles.private}>
              <Lock size={13} /> Only the wolves saw this
            </span>
          </header>
        ) : null}
        <p className={styles.text}>{text}</p>
      </div>
    </article>
  );
}
