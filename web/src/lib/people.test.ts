import { describe, expect, it } from "vitest";
import { avatarColor, roleColor } from "./people";

describe("roleColor", () => {
  it("gives every role its own colour", () => {
    const colours = ["Werewolf", "Seer", "Doctor", "Villager"].map(roleColor);
    expect(new Set(colours).size).toBe(4);
  });

  it("is the same wherever it is asked", () => {
    expect(roleColor("Seer")).toBe(roleColor("Seer"));
    expect(roleColor("Villager")).toBe("var(--role-villager)");
  });
});

describe("avatarColor", () => {
  it("is stable for a name", () => {
    expect(avatarColor("Hal")).toBe(avatarColor("Hal"));
  });
});
