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
};

/** A message in the wolves' private chat: an outlined bubble that says only the wolves saw it. */
export function WolfChat({ speaker, text, side, first, named, dim }: Props) {
  return (
    <article className={styles.row} data-side={side} data-first={first || undefined} data-dim={dim || undefined} data-static>
      {side === "in" ? <span className={styles.gutter}>{first ? <Avatar name={speaker} size={32} /> : null}</span> : null}
      <div className={styles.bubble} data-private>
        {first ? (
          <header className={styles.head}>
            {named ? (
              <span className={styles.name} style={{ color: side === "in" ? avatarColor(speaker) : undefined }}>
                {speaker}
              </span>
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
