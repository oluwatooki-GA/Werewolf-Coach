import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GameSummary } from "@/lib/api";
import { ChatList } from "./ChatList";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const game = (id: string, model: string, winner: "Wolves" | "Village") =>
  ({ id, model, winner, rounds: 3, cards: {}, rule_version: "v1" }) as unknown as GameSummary;

const games = [
  game("1-aaa", "gpt-4.1-nano", "Wolves"),
  game("1-bbb", "gpt-4.1-nano", "Village"),
  game("1-ccc", "claude-sonnet-5-5", "Village"),
  game("1-ddd", "gpt-4.1", "Wolves"),
];

const rows = () => screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("/games/"));

describe("ChatList", () => {
  it("pins the welcome chat, strategies, coach and play above the games", () => {
    render(<ChatList games={games} total={4} />);
    for (const name of ["Werewolf Coach Start", "Strategies The", "Coach The", "Play Take"]) {
      expect(screen.getByRole("link", { name: new RegExp(`^${name}.+`) })).toBeInTheDocument();
    }
  });

  it("lists the strongest model's games first", () => {
    render(<ChatList games={games} total={4} />);
    expect(rows().map((a) => a.getAttribute("href"))).toEqual([
      "/games/1-ccc",
      "/games/1-ddd",
      "/games/1-aaa",
      "/games/1-bbb",
    ]);
  });

  it("names a game plainly and says which model played it", () => {
    render(<ChatList games={games} total={4} />);
    const first = rows()[0] as HTMLElement;
    expect(first).toHaveTextContent("Game 1-ccc");
    expect(first).toHaveTextContent("Claude Sonnet 5.5");
    expect(first.textContent).not.toMatch(/seed/);
  });

  it("offers each model that played, best first, with its game count", () => {
    render(<ChatList games={games} total={4} />);
    const group = within(screen.getByRole("group", { name: "Filter by model" }));
    expect(group.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "All models",
      "Claude Sonnet 5.5 1",
      "GPT-4.1 1",
      "GPT-4.1 nano 2",
    ]);
  });

  it("shows only one model's games when you pick it", () => {
    render(<ChatList games={games} total={4} />);
    fireEvent.click(screen.getByRole("button", { name: /GPT-4.1 nano/ }));
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "All models" }));
    expect(rows()).toHaveLength(4);
  });

  it("combines the model and the winner", () => {
    render(<ChatList games={games} total={4} />);
    fireEvent.click(screen.getByRole("button", { name: /GPT-4.1 nano/ }));
    fireEvent.click(screen.getByRole("button", { name: "Village" }));
    expect(rows().map((a) => a.getAttribute("href"))).toEqual(["/games/1-bbb"]);
  });

  it("says so when no game matches", () => {
    render(<ChatList games={games} total={4} />);
    fireEvent.click(screen.getByRole("button", { name: /Claude Sonnet/ }));
    fireEvent.click(screen.getByRole("button", { name: "Wolves" }));
    expect(screen.getByText("No saved games match.")).toBeInTheDocument();
  });
});
