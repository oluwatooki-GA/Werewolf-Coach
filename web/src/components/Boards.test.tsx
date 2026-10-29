import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Generation } from "@/lib/api";
import { CardGraph } from "./CardGraph";
import { IntervalBar } from "./IntervalBar";
import { Revision } from "./Revision";

describe("IntervalBar", () => {
  it("says what it shows in words, with the interval", () => {
    render(<IntervalBar wins={14} games={19} enough of="Wolves won" />);
    const figure = screen.getByRole("img");
    expect(figure).toHaveAccessibleName(/Wolves won in 14 of 19 games, 74%/);
    expect(figure.getAttribute("aria-label")).toMatch(/95% interval runs from 5\d% to 8\d%/);
    expect(screen.queryByText("not clear yet")).toBeNull();
  });

  it("calls a thin sample not clear yet, in text and in the label", () => {
    const { container } = render(<IntervalBar wins={1} games={1} enough={false} of="Won" />);
    expect(screen.getByText("not clear yet")).toBeInTheDocument();
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/Not clear yet/);
    expect(container.querySelector("line[class*='thin']")).toBeTruthy(); // drawn dashed
  });

  it("copes with no games at all", () => {
    render(<IntervalBar wins={0} games={0} enough={false} of="Won" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/0 of 0 games, 0%/);
  });
});

describe("Revision", () => {
  const base = "Take the lead. Press again later. Never mention the wolf chat.";

  it("strikes through what was cut and marks what was added", () => {
    const { container } = render(
      <Revision
        base={base}
        changes={["- Take the lead.", "+ Never accuse your partner."]}
      />,
    );
    expect(container.querySelector("del")).toHaveTextContent("Take the lead.");
    expect(container.querySelector("ins")).toHaveTextContent("Added: Never accuse your partner.");
    expect(container.textContent).toContain("Press again later.");
    expect(container.querySelector("del")?.textContent).not.toContain("Press again");
  });

  it("never claims the coach changed nothing: an empty list may only mean it was not recorded", () => {
    render(<Revision base={base} changes={[]} />);
    expect(screen.queryByText(/changed nothing/i)).toBeNull();
    expect(screen.getByText(/Take the lead/)).toBeInTheDocument();
  });

  it("still shows what was cut when the base text is not on the site", () => {
    const { container } = render(<Revision base={null} changes={["- Old sentence."]} />);
    expect(container.querySelector("del")).toHaveTextContent("Old sentence.");
  });
});

describe("CardGraph", () => {
  const arm = (card: string, wins: number, games: number) => ({ card, seeds: [1], wins, games, clean: true, cost: "0", stopped: null });
  const gens = [
    {
      number: 1,
      champion_before: "wolf.accuse_early@2",
      champion_after: "wolf.accuse_early@2",
      challenger_card: "wolf.quiet_lead@1",
      promote: false,
      champion_arm: arm("wolf.accuse_early@2", 1, 1),
      challenger_arm: arm("wolf.quiet_lead@1", 0, 1),
    },
  ] as unknown as Generation[];

  it("draws each card with what it is in words, so it does not rely on colour", () => {
    render(<CardGraph generations={gens} />);
    expect(screen.getByText("accuse early")).toBeInTheDocument();
    expect(screen.getByText("v2, Starting champion")).toBeInTheDocument();
    expect(screen.getByText("v1, Not better, dropped")).toBeInTheDocument();
  });

  it("says how a card did and that a thin sample is not clear yet", () => {
    render(<CardGraph generations={gens} />);
    expect(screen.getByText("Won 0 of 1 game, not clear yet")).toBeInTheDocument();
  });

  it("describes the whole tree to a screen reader", () => {
    render(<CardGraph generations={gens} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/accuse early, version 2, Starting champion.*quiet lead, version 1, Not better, dropped/);
  });

  it("links a generated card to its generation in the thread, and the start card to nothing", () => {
    render(<CardGraph generations={gens} />);
    expect(screen.getByRole("link", { name: "Generation 1: quiet lead" })).toHaveAttribute("href", "#g1");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("draws nothing before the coach has run", () => {
    const { container } = render(<CardGraph generations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
