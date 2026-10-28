"use client";

import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Post } from "@/components/Post";
import styles from "./notice.module.css";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <ChatPage avatar={<ChatAvatar kind="welcome" size={40} />} title="Connection lost">
      <div role="alert">
        <Post name="Lab" bot>
          <p>The site could not reach its data. The API may be starting up or stopped. Wait a moment and try again.</p>
          <button type="button" className={styles.action} onClick={reset}>
            Try again
          </button>
        </Post>
      </div>
    </ChatPage>
  );
}
