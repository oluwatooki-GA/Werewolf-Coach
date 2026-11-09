import Link from "next/link";
import { Back, Github } from "./Icons";
import styles from "./ChatHeader.module.css";

const REPO = "https://github.com/oluwatooki-GA/Werewolf-Coach";

type Props = {
  avatar: React.ReactNode;
  title: string;
  /** One quiet line under the title: who is in the chat, or what it is for. */
  subtitle?: React.ReactNode;
  /** Buttons and chips on the right. */
  actions?: React.ReactNode;
  /** Makes the avatar and title a button (the chat's info). */
  onInfo?: () => void;
  infoLabel?: string;
};

/** The bar over an open chat: back arrow on a phone, picture, name, a line of detail, actions. */
export function ChatHeader({ avatar, title, subtitle, actions, onInfo, infoLabel }: Props) {
  const who = (
    <>
      {avatar}
      <span className={styles.who}>
        <h1>{title}</h1>
        {subtitle ? <span className={styles.sub}>{subtitle}</span> : null}
      </span>
    </>
  );
  return (
    <header className={styles.bar}>
      <Link href="/" className={styles.back} aria-label="Back to the chats">
        <Back />
      </Link>
      {onInfo ? (
        <button type="button" className={styles.identity} onClick={onInfo} aria-label={infoLabel}>
          {who}
        </button>
      ) : (
        <div className={styles.identity}>{who}</div>
      )}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
      <a
        href={REPO}
        className={styles.github}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Werewolf Coach on GitHub (opens in a new tab)"
      >
        <Github />
      </a>
    </header>
  );
}
