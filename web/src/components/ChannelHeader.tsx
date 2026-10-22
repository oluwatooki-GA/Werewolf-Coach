import styles from "./ChannelHeader.module.css";

/** The bar at the top of a page, like a chat channel's: its name and a one-line topic. */
export function ChannelHeader({
  name,
  topic,
  children,
}: {
  name: string;
  topic?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className={styles.bar}>
      <h1>
        <span aria-hidden="true">#</span> {name}
      </h1>
      {topic ? <p>{topic}</p> : null}
      {children ? <div className={styles.extra}>{children}</div> : null}
    </header>
  );
}
