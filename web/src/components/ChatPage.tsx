import { ChatHeader } from "./ChatHeader";
import styles from "./ChatPage.module.css";

type Props = {
  avatar: React.ReactNode;
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
};

/** A chat that is not a game: the header, then a scrolling thread on the wallpaper. */
export function ChatPage({ avatar, title, subtitle, actions, children }: Props) {
  return (
    <div className={styles.page}>
      <ChatHeader avatar={avatar} title={title} subtitle={subtitle} actions={actions} />
      <div className={styles.body}>
        <div className={styles.thread}>{children}</div>
      </div>
    </div>
  );
}
