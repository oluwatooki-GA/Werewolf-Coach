import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

  it("says so when nothing changed", () => {
    render(<Revision base={base} changes={[]} />);
    expect(screen.getByText("The coach changed nothing in this card.")).toBeInTheDocument();
  });

  it("still shows what was cut when the base text is not on the site", () => {
    const { container } = render(<Revision base={null} changes={["- Old sentence."]} />);
    expect(container.querySelector("del")).toHaveTextContent("Old sentence.");
  });
});
