import { Avatar } from "./Avatar";
import styles from "./Post.module.css";

/** A message from the coach or the lab (a bot), with an optional embedded card under its text. */
export function Post({
  name,
  bot = false,
  children,
}: {
  name: string;
  bot?: boolean;
  children: React.ReactNode;
}) {
  return (
    <article className={styles.post}>
      <Avatar name={name} />
      <div className={styles.body}>
        <header>
          <b>{name}</b>
          {bot ? <span className={styles.bot}>Bot</span> : null}
        </header>
        {children}
      </div>
    </article>
  );
}

export function Embed({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className={styles.embed}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}
