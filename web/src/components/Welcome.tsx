import { Room } from "@/components/Room";
import { apiOrNull } from "@/lib/api";
import type { Featured, Replay } from "@/lib/api";
import { BOT_NAME, type BotNote, type Playable } from "@/lib/playback";
import { excerpt, welcomeNotes } from "@/lib/replay";
import { ChatAvatar } from "./ChatAvatar";

const note = (text: string): BotNote => ({ kind: "bot", text, round: 0 });

/**
 * The first chat a visitor sees. The Werewolf Coach bot says what this is, plays one real moment
 * (a wolf claiming to be the Seer) and then points at the bubble to tap. The moment is the
 * featured line of a stored game, so nothing here is made up.
 */
export async function Welcome() {
  const featured = await apiOrNull<Featured>("/featured");
  const replay = featured ? await apiOrNull<Replay>(`/games/${featured.game_id}/replay`) : null;

  if (!replay || !featured) {
    return (
      <Room
        entries={[
          note("Hi, I'm the Werewolf Coach. In this lab, eight AI agents play Werewolf in a group chat."),
          note("No game with a lie and a private note is stored yet. Seed the database with app seed and reload."),
        ]}
        players={[]}
        title={BOT_NAME}
        subtitle="A lab for AI Werewolf"
        avatar={<ChatAvatar kind="welcome" size={40} />}
        story
        label="Welcome chat"
      />
    );
  }

  const notes = welcomeNotes(replay.entries, featured.focus);
  const entries: Playable[] = [
    ...notes.before.map(note),
    ...excerpt(replay.entries, featured.focus),
    ...notes.after.map(note),
  ];
  return (
    <Room
      entries={entries}
      players={replay.players}
      title={BOT_NAME}
      subtitle="A lab for AI Werewolf"
      avatar={<ChatAvatar kind="welcome" size={40} />}
      startAt={featured.focus}
      story
      label="Welcome chat"
    />
  );
}
