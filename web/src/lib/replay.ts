import type { ReplayEntry } from "./api";

/**
 * A few entries around one line, for the home page: the setup before it (the wolves' plan, the
 * morning) and the replies after it. Falls back to the start of the game if the line is missing.
 */
export function excerpt(entries: ReplayEntry[], focus: string, before = 1, after = 4): ReplayEntry[] {
  const at = entries.findIndex((e) => e.kind === "line" && e.ref === focus);
  const index = at === -1 ? 0 : at;
  return entries.slice(Math.max(0, index - before), index + after + 1);
}

/**
 * What the Werewolf Coach bot says around the featured moment in the welcome chat: first what
 * this is, then, after the moment has played, who lied and where to tap. The second note is built
 * from the featured line itself, never hard-coded.
 */
export function welcomeNotes(entries: ReplayEntry[], focus: string): { before: string[]; after: string[] } {
  const line = entries.find((e) => e.kind === "line" && e.ref === focus);
  const before = [
    "Hi, I'm the Werewolf Coach. In this lab, eight AI agents play Werewolf in a group chat. Two of them are secretly wolves and lie to the rest.",
    "Here is a moment from a real game. Can you tell who is lying?",
  ];
  const lie =
    line && line.kind === "line"
      ? `${line.speaker} is ${line.role === "Werewolf" ? "a wolf" : `the ${line.role}`}. ${
          line.claim ? `It claimed to be the ${line.claim.role}, which was a lie.` : "That message was a lie."
        } Tap the bubble to read what ${line.speaker} was thinking when it sent it.`
      : "Tap any message to read what its player was thinking when it sent it.";
  return {
    before,
    after: [lie, "The chat is public, the thoughts are not. Open any game in the list to watch it play, or see how the strategies and the coach did."],
  };
}
