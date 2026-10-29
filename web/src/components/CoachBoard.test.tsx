import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Card, CardResult, Generation } from "@/lib/api";
import { CoachBoard } from "./CoachBoard";

vi.mock("next/navigation", () => ({ usePathname: () => "/coach/wolf" }));

const card = (id: string, version: string, summary: string, extra: Partial<Card> = {}) =>
  ({
    id,
    version,
    role: id.startsWith("wolf.") ? "Werewolf" : "Villager",
    source: `Source of ${id}`,
    summary,
    instructions: `Instructions for ${id}.`,
    expected_moves: [],
    parent: null,
    ...extra,
  }) as unknown as Card;

const cards = [
  card("wolf.accuse_early", "2", "Accuse early."),
  card("wolf.lie_low", "1", "Stay unnoticed."),
  card("wolf.coach_smoke_g1", "1", "A coach card."), // written by the coach, so it hangs under its parent
];

const arm = (c: string, wins: number, games: number) => ({ card: c, seeds: [1], wins, games, clean: true, cost: "0.03", stopped: null });

const generations = [
  {
    side: "wolf",
    number: 1,
    champion_before: "wolf.accuse_early@2",
    champion_after: "wolf.accuse_early@2",
    evidence: "4 of 5 lost games",
    diagnosis: "The wolves turned on each other.",
    challenger_card: "wolf.coach_smoke_g1@1",
    challenger_text: "Wolves agree on one kill.",
    changes: [],
    check: { attempts: 1, passed: true, reasons: [] },
    champion_arm: arm("wolf.accuse_early@2", 1, 1),
    challenger_arm: arm("wolf.coach_smoke_g1@1", 0, 1),
    promote: false,
    decision: "no better: challenger 0/1 against champion 1/1",
    coach_cost: "0.025",
  },
] as unknown as Generation[];

const results = [
  { card: "wolf.accuse_early@2", role: "Werewolf", rule_version: "v1", games: 19, wins: 14, rate: 0.74, low: 0.5, high: 0.9, enough: true },
] as CardResult[];

const sides = [
  { id: "wolf", label: "Wolves" },
  { id: "villager", label: "Villagers" },
];

function open() {
  return render(<CoachBoard side="wolf" label="Wolves" sides={sides} cards={cards} generations={generations} results={results} />);
}

const wait = (ms: number) => {
  for (let t = 0; t < ms; t += 100) act(() => void vi.advanceTimersByTime(100));
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("the coach's cards", () => {
  it("starts with just the cards the coach can start from, not the ones it wrote", () => {
    open();
    expect(screen.getByRole("button", { name: /accuse early/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /lie low/ })).toBeInTheDocument();
    expect(screen.queryByText("coach smoke g1")).toBeNull();
  });

  it("shows no thoughts, no details and no tree until you pick something", () => {
    open();
    expect(screen.getByLabelText("Details")).toHaveAttribute("hidden");
    expect(screen.queryByText(/The coach's thoughts/)).toBeNull();
    expect(screen.queryByRole("group", { name: /family tree/ })).toBeNull();
  });

  it("rings the current champion and says how much the coach built from each card", () => {
    open();
    const tile = screen.getByRole("button", { name: /accuse early/ });
    expect(tile).toHaveAttribute("data-champion");
    expect(tile).toHaveTextContent("Current champion. The coach built 1 card from it.");
    expect(screen.getByRole("button", { name: /lie low/ })).toHaveTextContent("The coach has not built on it yet.");
  });

  it("shows the cards built from the one you pick as a tree", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /accuse early/ }));
    expect(screen.getByRole("group", { name: /family tree/ })).toBeInTheDocument();
    expect(screen.getByText("coach smoke g1")).toBeInTheDocument();
    expect(screen.getByText("Cards built from accuse early")).toBeInTheDocument();
  });

  it("goes back to all the cards", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /accuse early/ }));
    fireEvent.click(screen.getByRole("button", { name: "All cards" }));
    expect(screen.getByRole("button", { name: /lie low/ })).toBeInTheDocument();
  });

  it("says plainly when the coach has not built on a card yet", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /lie low/ }));
    expect(screen.getByText(/The coach has not built on this card yet/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /family tree/ })).toBeNull();
  });
});

describe("a card's details", () => {
  const pick = (name: RegExp) => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /accuse early/ }));
    fireEvent.click(screen.getByRole("button", { name }));
  };

  it("opens the card's text, source and how it did in the saved games", () => {
    pick(/^accuse early, version 2\./);
    const info = within(screen.getByLabelText("Details"));
    expect(info.getByText("Instructions for wolf.accuse_early.")).toBeInTheDocument();
    expect(info.getByText("Source of wolf.accuse_early")).toBeInTheDocument();
    expect(info.getByRole("img", { name: /Wolves won in 14 of 19 games/ })).toBeInTheDocument();
  });

  it("gives the starting card no coach thoughts, since the coach did not write it", () => {
    pick(/^accuse early, version 2\./);
    expect(screen.queryByLabelText("The coach's thoughts")).toBeNull();
  });

  it("closes", () => {
    pick(/^accuse early, version 2\./);
    fireEvent.click(within(screen.getByLabelText("Details")).getByRole("button", { name: "Close" }));
    expect(screen.getByLabelText("Details")).toHaveAttribute("hidden");
  });
});

describe("the coach's thoughts", () => {
  const pickCoachCard = () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /accuse early/ }));
    fireEvent.click(screen.getByRole("button", { name: /^coach smoke g1, version 1\./ }));
  };

  it("shows that the coach is typing before anything is said", () => {
    pickCoachCard();
    expect(screen.getByText("Coach is typing…")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Coach is typing");
    expect(screen.queryByText(/I read 4 of 5 lost games/)).toBeNull();
  });

  it("says what it read first, then what it concluded, one message at a time", () => {
    pickCoachCard();
    wait(1000);
    expect(screen.getByText(/I read 4 of 5 lost games/)).toBeInTheDocument();
    expect(screen.queryByText("The wolves turned on each other.")).toBeNull();
    wait(1400);
    expect(screen.getByText("The wolves turned on each other.")).toBeInTheDocument();
  });

  it("ends with the result and the verdict, and stops typing", () => {
    pickCoachCard();
    wait(8000);
    expect(screen.getByText(/Champion stays\./)).toBeInTheDocument();
    expect(screen.queryByText("Coach is typing…")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows everything at once when the reader asks for less motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    pickCoachCard();
    expect(screen.getByText(/Champion stays\./)).toBeInTheDocument();
    expect(screen.queryByText("Coach is typing…")).toBeNull();
    vi.unstubAllGlobals();
  });

  it("starts again for a different card", () => {
    pickCoachCard();
    wait(8000);
    fireEvent.click(screen.getByRole("button", { name: /^accuse early, version 2\./ }));
    expect(screen.queryByLabelText("The coach's thoughts")).toBeNull();
  });
});

describe("the layout", () => {
  it("keeps the cards in the page when one is picked, folded to a rail beside the tree", () => {
    const { container } = open();
    expect(container.querySelector("[data-folded]")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /accuse early/ }));
    expect(container.querySelector("[data-folded]")).not.toBeNull();
    expect(screen.getByRole("button", { name: /lie low/ })).toBeInTheDocument();
  });

  it("marks the picked card in the rail, and picking another moves the tree to it", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /^accuse early version 2/ }));
    expect(screen.getByRole("button", { name: /^accuse early version 2/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: /^lie low version 1/ }));
    expect(screen.getByText("Cards built from lie low")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /family tree/ })).toBeNull();
  });

  it("unfolds the rail again when you tap the picked card a second time", () => {
    const { container } = open();
    fireEvent.click(screen.getByRole("button", { name: /^accuse early version 2/ }));
    fireEvent.click(screen.getByRole("button", { name: /^accuse early version 2/ }));
    expect(container.querySelector("[data-folded]")).toBeNull();
  });
});
