"use client";

import { useRouter } from "next/navigation";
import { startTransition } from "react";
import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Post } from "@/components/Post";
import { Waker } from "@/components/Waker";
import styles from "./notice.module.css";

/** A page that could not get its data: most often the API is waking up, so it asks again by itself. */
export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  const retry = () =>
    startTransition(() => {
      router.refresh();
      reset();
    });
  return (
    <ChatPage avatar={<ChatAvatar kind="welcome" size={40} />} title="Connection lost">
      <div role="alert">
        <Post name="Lab" bot>
          <p>The site could not reach its data. The API may be starting up or stopped.</p>
          <button type="button" className={styles.action} onClick={retry}>
            Try again
          </button>
        </Post>
      </div>
      <Waker onUp={retry} />
    </ChatPage>
  );
}
