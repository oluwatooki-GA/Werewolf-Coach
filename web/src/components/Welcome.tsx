import { Room } from "@/components/Room";
import { apiOrNull, isAsleep } from "@/lib/api";
import type { Featured, Replay } from "@/lib/api";
import { bundledReplay, featured as saved } from "@/lib/featured";
import { BOT_NAME, type BotNote, type Playable } from "@/lib/playback";
import { excerpt, welcomeNotes } from "@/lib/replay";
import { ChatAvatar } from "./ChatAvatar";

const note = (text: string): BotNote => ({ kind: "bot", text, round: 0 });

/** The moment to play: from the API, or from the copy saved in the site while the API is asleep. */
async function pickMoment(): Promise<{ featured: Featured | null; replay: Replay | null }> {
  try {
    const live = await apiOrNull<Featured>("/featured");
    return { featured: live, replay: live ? await apiOrNull<Replay>(`/games/${live.game_id}/replay`) : null };
  } catch (error) {
    if (!isAsleep(error)) throw error;
    return { featured: saved.welcome, replay: await bundledReplay(saved.welcome.game_id) };
  }
}

/**
 * The first chat a visitor sees. The Werewolf Coach bot says what this is, plays one real moment
 * (a wolf claiming to be the Seer) and then points at the bubble to tap. The moment is the
 * featured line of a stored game, so nothing here is made up.
 */
export async function Welcome() {
  const { featured, replay } = await pickMoment();

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
