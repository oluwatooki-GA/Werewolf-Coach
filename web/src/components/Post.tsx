import { avatarColor } from "@/lib/people";
import { Avatar } from "./Avatar";
import styles from "./Message.module.css";
import own from "./Post.module.css";

/**
 * A message from the Werewolf Coach, the coach or the lab (a bot): an incoming bubble, with the
 * bot's name over the first of a run. Cards and results go inside it as an `Embed`.
 */
export function Post({
  name,
  bot = false,
  first = true,
  children,
}: {
  name: string;
  bot?: boolean;
  /** First bubble of a run by the same sender: it gets the name, the avatar and the tail. */
  first?: boolean;
  children: React.ReactNode;
}) {
  return (
    <article className={styles.row} data-side="in" data-first={first || undefined} data-static>
      <span className={styles.gutter}>{first ? <Avatar name={name} size={32} /> : null}</span>
      <div className={`${styles.bubble} ${own.bubble}`}>
        {first ? (
          <header className={styles.head}>
            <span className={styles.name} style={{ color: avatarColor(name) }}>
              {name}
            </span>
            {bot ? <span className={own.bot}>Bot</span> : null}
          </header>
        ) : null}
        <div className={own.body}>{children}</div>
      </div>
    </article>
  );
}

/** A card, a diff or a result inside a bot's bubble, like the preview a messenger unfurls. */
export function Embed({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className={own.embed}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}
