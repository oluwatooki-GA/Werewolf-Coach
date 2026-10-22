/** How players look in the chat: a stable avatar colour and a colour per role. */

const AVATARS = ["#e8776f", "#e3a65a", "#9bc96e", "#52bfa5", "#5eaee8", "#928ee8", "#c97bd6", "#d97aa6"];

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

/** The role's tag colour: coral wolves, gold Seer, green Doctor, slate Villager. */
export function roleColor(role: string): string {
  switch (role) {
    case "Werewolf":
      return "var(--wolf)";
    case "Seer":
      return "var(--gold)";
    case "Doctor":
      return "var(--green)";
    default:
      return "var(--slate)";
  }
}
