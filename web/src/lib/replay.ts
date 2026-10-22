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
 * What the home page's guided demo says as it plays: first the chat looks ordinary, then the
 * roles are revealed at the featured message, then it points at the next step. Built from the
 * featured line itself, never hard-coded.
 */
export function storyCaption(
  entries: ReplayEntry[],
  focus: string,
  shown: number,
  total: number,
): string {
  const at = entries.findIndex((e) => e.kind === "line" && e.ref === focus);
  const line = at >= 0 ? entries[at] : undefined;
  if (shown >= total && total > 0) {
    return "That was one moment from a real game. Click any message to read what its player was thinking, or watch the whole game.";
  }
  if (at < 0 || shown <= at || !line || line.kind !== "line") {
    return "Eight AI players are chatting in a game of Werewolf. Two of them are secretly wolves who lie to the rest. Can you tell which?";
  }
  const who = line.role === "Werewolf" ? "a wolf" : `the ${line.role}`;
  const did = line.claim ? `claimed to be the ${line.claim.role}, which was a lie` : "lied";
  return `${line.speaker} is ${who}. It just ${did}. On the right is what it was thinking when it sent that message.`;
}
