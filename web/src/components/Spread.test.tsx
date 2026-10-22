import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Replay } from "@/lib/api";
import fixture from "../test/replay.fixture.json";
import { Spread } from "./Spread";

const replay = fixture as unknown as Replay;

function open(props: Partial<React.ComponentProps<typeof Spread>> = {}) {
  return render(
    <Spread
      entries={replay.entries}
      players={replay.players}
      showNotes
      label="A recorded game"
      {...props}
    />,
  );
}

describe("Spread", () => {
  it("numbers each public line the way the game cites it", () => {
    open();
    for (const ref of ["R1-1", "R1-2", "R1-3"]) {
      expect(document.getElementById(ref)).toBeInTheDocument();
    }
  });

  it("puts the private note beside the line it belongs to", () => {
    open();
    expect(screen.getByLabelText("Private notes for R1-1")).toHaveTextContent(
      "Claimed Seer to gain trust and deflect suspicion.",
    );
  });

  it("states what the lab found about a lie, in words", () => {
    open();
    const notes = screen.getByLabelText("Private notes for R1-1");
    expect(within(notes).getByText(/the claimed check does not match the log/i)).toBeInTheDocument();
  });

  it("marks a lie with the word as well as a colour", () => {
    open();
    const line = document.getElementById("R1-1");
    expect(line?.querySelector("p[data-lie]")).toBeTruthy();
    expect(line).toHaveTextContent("lie");
  });

  it("shows a team by a mark and a word, never colour alone", () => {
    open();
    const hal = document.getElementById("R1-1");
    expect(hal).toHaveTextContent("Hal");
    expect(within(hal as HTMLElement).getByText("Wolves")).toHaveClass("visually-hidden");
  });

  it("hides every private note, the wolf chat and the night when sealed", () => {
    open({ showNotes: false });
    expect(screen.queryByLabelText("Wolf chat")).toBeNull();
    expect(screen.queryByLabelText("The night")).toBeNull();
    expect(screen.queryByLabelText("Private notes for R1-1")).toBeNull();
    expect(document.getElementById("R1-1")).toBeInTheDocument(); // the public script stays
  });

  it("groups the wolf chat, the Seer's check and the night into one block", () => {
    open();
    expect(screen.getAllByLabelText("Wolf chat")).toHaveLength(2);
    expect(screen.getByLabelText("Seer result")).toHaveTextContent("learns that");
    expect(screen.getByLabelText("The night")).toBeInTheDocument();
  });

  it("highlights the line you click and lets the last one fade", () => {
    vi.useFakeTimers();
    open();
    const one = document.getElementById("R1-1") as HTMLElement;
    const two = document.getElementById("R1-2") as HTMLElement;
    fireEvent.click(one);
    expect(one).toHaveAttribute("data-glow", "now");
    fireEvent.click(two);
    expect(two).toHaveAttribute("data-glow", "now");
    expect(one).toHaveAttribute("data-glow", "fade");
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(one).not.toHaveAttribute("data-glow");
    vi.useRealTimers();
  });

  it("moves between lines with the arrow keys", () => {
    open();
    const one = document.getElementById("R1-1") as HTMLElement;
    one.focus();
    fireEvent.keyDown(one, { key: "ArrowDown" });
    expect(document.activeElement).toBe(document.getElementById("R1-2"));
    fireEvent.keyDown(document.getElementById("R1-2") as HTMLElement, { key: "ArrowUp" });
    expect(document.activeElement).toBe(one);
  });

  it("opens with a chosen line highlighted", () => {
    open({ startAt: "R1-2" });
    expect(document.getElementById("R1-2")).toHaveAttribute("data-glow", "now");
  });

  it("links a cited line only when that line is on the page", () => {
    open();
    const cites = document.getElementById("R1-2")?.querySelector("a[href='#R1-1']");
    expect(cites).toBeTruthy();
  });

  it("leaves out round headings for an excerpt", () => {
    open({ acts: false });
    expect(screen.queryByRole("heading", { name: /round 1/i })).toBeNull();
  });
});
