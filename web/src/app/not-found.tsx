import Link from "next/link";
import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Post } from "@/components/Post";
import styles from "./notice.module.css";

export default function NotFound() {
  return (
    <ChatPage avatar={<ChatAvatar kind="welcome" size={40} />} title="Not found">
      <Post name="Lab" bot>
        <p>There is nothing at this address. The game may have been removed, or the link may be mistyped.</p>
        <Link href="/games" className={styles.action}>
          Back to the games
        </Link>
      </Post>
    </ChatPage>
  );
}
