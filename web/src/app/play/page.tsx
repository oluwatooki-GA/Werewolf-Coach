import type { Metadata } from "next";
import { ChatAvatar } from "@/components/ChatAvatar";
import { ChatPage } from "@/components/ChatPage";
import { Pill } from "@/components/Pill";
import { Post } from "@/components/Post";
import { api } from "@/lib/api";
import type { PlayStatus } from "@/lib/api";

/** Reads live data from the API, so it is rendered per request, never at build time. */
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Play" };

export default async function PlayPage() {
  const status = await api<PlayStatus>("/play/status");
  return (
    <ChatPage
      avatar={<ChatAvatar kind="play" size={40} />}
      title="Play"
      subtitle="Take a seat at the table against seven AI players"
    >
      {status.available ? (
        <Post name="Lab" bot>
          <p>Play mode is open.</p>
        </Post>
      ) : (
        <>
          <Post name="Lab" bot>
            <p>
              Play mode is not built yet. When it is, you will join a game as one of the eight players, with a turn
              timer, and the finished game will open here as a chat with everyone&apos;s private notes.
            </p>
          </Post>
          <Pill>The server says: {status.reason}.</Pill>
        </>
      )}
    </ChatPage>
  );
}
