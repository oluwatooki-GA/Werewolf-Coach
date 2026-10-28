/** How players look in the chat: a stable avatar colour and a colour per role. */

// eight hues at one lightness and one softness, so no avatar shouts over the others
const AVATARS = ["#d4ac7a", "#c9c27a", "#a9bf86", "#7fbfae", "#84aed6", "#a09fda", "#bc95c9", "#9fb4c4"];

/** The same name always gets the same avatar colour (FNV-1a, then a final mix). */
export function avatarColor(name: string): string {
  let hash = 2166136261;
  for (const char of name) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 15), 2246822519) >>> 0;
  hash ^= hash >>> 13;
  return AVATARS[(hash >>> 0) % AVATARS.length] ?? "#5eaee8";
}

export function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase();
}

/** Every role has its own colour: coral wolves, sky Seer, lime Doctor, teal Villager. */
export function roleColor(role: string): string {
  switch (role) {
    case "Werewolf":
      return "var(--role-wolf)";
    case "Seer":
      return "var(--role-seer)";
    case "Doctor":
      return "var(--role-doctor)";
    default:
      return "var(--role-villager)";
  }
}
