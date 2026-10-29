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
    for (const name of ["Werewolf Coach Start", "Strategies The", "Coach The", "Play Pick the cards"]) {
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


describe("the Play chat", () => {
  it("is open for use, not marked as coming soon, and says what it does", () => {
    render(<ChatList games={games} total={4} />);
    const play = screen.getByRole("link", { name: /^Play/ });
    expect(play).toHaveTextContent("Pick the cards, watch the agents play");
    expect(play).not.toHaveTextContent("soon");
    expect(play).not.toHaveTextContent("seat");
  });
});

const made = (id: string, model: string, rounds: number, source = "experiment") =>
  ({ id, model, winner: "Village", rounds, cards: {}, rule_version: "v3", source }) as unknown as GameSummary;

const mixed = [
  made("2-aaa", "gpt-4.1-mini", 3),
  made("2-bbb", "gpt-4.1-mini", 5),
  made("2-ccc", "claude-sonnet-5-5", 2),
  made("2-ddd", "gpt-4o-mini", 5, "play"),
  made("2-eee", "gpt-4.1-mini", 2),
];
const ids = () => rows().map((a) => a.getAttribute("href")?.replace("/games/", ""));
const sortBy = (name: string) =>
  fireEvent.click(within(screen.getByRole("group", { name: "Sort games" })).getByRole("button", { name }));

describe("sorting the games", () => {
  it("offers a sort, starting on the strongest model first", () => {
    render(<ChatList games={mixed} total={5} />);
    const group = within(screen.getByRole("group", { name: "Sort games" }));
    expect(group.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Strongest model",
      "Played here first",
      "Most rounds",
      "Fewest rounds",
    ]);
    expect(group.getByRole("button", { name: "Strongest model" })).toHaveAttribute("aria-pressed", "true");
    expect(ids()[0]).toBe("2-ccc");
  });

  it("puts the longest games first, and keeps the earlier order between equals", () => {
    render(<ChatList games={mixed} total={5} />);
    sortBy("Most rounds");
    expect(ids()).toEqual(["2-bbb", "2-ddd", "2-aaa", "2-ccc", "2-eee"]);
    expect(within(screen.getByRole("group", { name: "Sort games" })).getByRole("button", { name: "Most rounds" })).toHaveAttribute("aria-pressed", "true");
  });

  it("puts the shortest games first", () => {
    render(<ChatList games={mixed} total={5} />);
    sortBy("Fewest rounds");
    expect(ids()).toEqual(["2-ccc", "2-eee", "2-aaa", "2-bbb", "2-ddd"]);
  });

  it("puts games played on this site first, then the rest as before", () => {
    render(<ChatList games={mixed} total={5} />);
    sortBy("Played here first");
    expect(ids()).toEqual(["2-ddd", "2-ccc", "2-aaa", "2-bbb", "2-eee"]);
  });

  it("goes back to the strongest model first", () => {
    render(<ChatList games={mixed} total={5} />);
    sortBy("Most rounds");
    sortBy("Strongest model");
    expect(ids()[0]).toBe("2-ccc");
  });

  it("sorts only the games that the filters leave", () => {
    render(<ChatList games={mixed} total={5} />);
    fireEvent.click(screen.getByRole("button", { name: /GPT-4.1 mini/ }));
    sortBy("Most rounds");
    expect(ids()).toEqual(["2-bbb", "2-aaa", "2-eee"]);
  });
});
