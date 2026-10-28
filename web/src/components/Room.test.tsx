import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { Replay } from "@/lib/api";
import fixture from "../test/replay.fixture.json";
import { Room } from "./Room";

const replay = fixture as unknown as Replay;

function open(props: Partial<React.ComponentProps<typeof Room>> = {}) {
  return render(
    <Room
      entries={replay.entries}
      players={replay.players}
      title="seed-1-845496ae"
      avatar={<span />}
      label="A recorded game"
      autoplay={false}
      {...props}
    />,
  );
}

const panel = () => within(screen.getByLabelText("Details"));
const menu = () => fireEvent.click(screen.getByRole("button", { name: "Chat options" }));
const players = () => fireEvent.click(screen.getByRole("button", { name: "Players" }));

beforeEach(() => {
  try {
    localStorage.clear();
  } catch {
    // no storage in this environment
  }
});

describe("Room", () => {
  it("posts every public line as a message with its number and speaker", () => {
    open();
    for (const ref of ["R1-1", "R1-2", "R1-3"]) {
      expect(document.getElementById(ref)).toBeInTheDocument();
    }
    expect(document.getElementById("R1-1")).toHaveTextContent("Hal");
    expect(document.getElementById("R1-1")).toHaveTextContent("I am the Seer.");
  });

  it("opens a round as a divider with the round's name", () => {
    open();
    expect(screen.getByRole("heading", { name: "Round 1" })).toBeInTheDocument();
  });

  it("opens Message info with the private note when you tap a message", () => {
    open();
    expect(screen.getByLabelText("Details")).toHaveAttribute("hidden");
    fireEvent.click(document.getElementById("R1-1") as HTMLElement);
    expect(screen.getByLabelText("Details")).not.toHaveAttribute("hidden");
    expect(panel().getByRole("heading", { name: "Message info" })).toBeInTheDocument();
    expect(panel().getByText("Claimed Seer to gain trust and deflect suspicion.")).toBeInTheDocument();
    expect(panel().getByText(/the claimed check does not match the log/i)).toBeInTheDocument();
    expect(document.getElementById("R1-1")).toHaveAttribute("aria-current", "true");
  });

  it("closes Message info and clears the selection", () => {
    open();
    fireEvent.click(document.getElementById("R1-1") as HTMLElement);
    fireEvent.click(panel().getByRole("button", { name: "Close" }));
    expect(screen.getByLabelText("Details")).toHaveAttribute("hidden");
    expect(document.getElementById("R1-1")).not.toHaveAttribute("aria-current");
  });

  it("opens with a chosen message already selected, and its info showing", () => {
    open({ startAt: "R1-2" });
    expect(document.getElementById("R1-2")).toHaveAttribute("aria-current", "true");
    expect(screen.getByLabelText("Details")).not.toHaveAttribute("hidden");
    expect(panel().getByLabelText("Private thoughts of Fay")).toBeInTheDocument();
  });

  it("tags each speaker with the role in words and a drawn team mark", () => {
    open();
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(within(hal).getByText("Werewolf")).toBeInTheDocument();
    expect(hal.querySelector("svg path")).toBeTruthy();
  });

  it("flags a lie in words and underlines it, never by colour alone", () => {
    open();
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(hal).toHaveAttribute("data-lie");
    expect(within(hal).getByText("lie")).toBeInTheDocument();
  });

  it("quotes a cited line inside the reply, with who said it", () => {
    open();
    const fay = document.getElementById("R1-2") as HTMLElement;
    const quote = fay.querySelector("a[href='#R1-1']");
    expect(quote).toHaveTextContent("Hal");
    expect(quote).toHaveTextContent("I am the Seer");
  });

  it("shows the wolf chat and the night as private, marked as such", () => {
    open();
    expect(screen.getAllByText(/Only the wolves saw this/)).toHaveLength(2);
    expect(screen.getByText(/The wolves chose Eve/)).toBeInTheDocument();
  });

  it("hides roles, the lab's findings, wolf chat and private notes in the public view", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(within(hal).queryByText("Werewolf")).toBeNull();
    expect(within(hal).queryByText("lie")).toBeNull();
    expect(hal).not.toHaveAttribute("data-lie");
    expect(screen.queryByText(/Only the wolves saw this/)).toBeNull();
    expect(panel().getByText(/Roles and private notes are hidden/)).toBeInTheDocument();
  });

  it("keeps tokens and moves behind 'Show moves'", () => {
    open();
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(within(hal).queryByText(/token/)).toBeNull();
    menu();
    fireEvent.click(screen.getByLabelText("Show moves"));
    expect(within(hal).getByText(/token/)).toBeInTheDocument();
  });

  it("lists the players once, each with their role in words and a team mark", () => {
    open();
    players();
    const members = panel().getByLabelText("Players");
    expect(within(members).getByRole("heading", { name: "Players, 8 players" })).toBeInTheDocument();
    expect(within(members).getAllByRole("button")).toHaveLength(8);
    expect(within(members).getAllByText("Werewolf")).toHaveLength(2);
    expect(within(members).getByText("Seer")).toBeInTheDocument();
  });

  it("follows one player: everyone else's messages dim, and clicking again clears it", () => {
    open();
    players();
    const hal = within(panel().getByLabelText("Players")).getByRole("button", { name: /Hal/ });
    fireEvent.click(hal);
    expect(hal).toHaveAttribute("aria-pressed", "true");
    expect(document.getElementById("R1-2")).toHaveAttribute("data-dim");
    expect(document.getElementById("R1-1")).not.toHaveAttribute("data-dim");
    fireEvent.click(hal);
    expect(document.getElementById("R1-2")).not.toHaveAttribute("data-dim");
  });

  it("moves between messages with the arrow keys, selecting as it goes", () => {
    open();
    const one = document.getElementById("R1-1") as HTMLElement;
    one.focus();
    fireEvent.keyDown(one, { key: "ArrowDown" });
    expect(document.activeElement).toBe(document.getElementById("R1-2"));
    expect(document.getElementById("R1-2")).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(document.getElementById("R1-2") as HTMLElement, { key: "ArrowUp" });
    expect(document.activeElement).toBe(one);
  });

  it("selects with Enter and clears with Escape", () => {
    open();
    const one = document.getElementById("R1-1") as HTMLElement;
    one.focus();
    fireEvent.keyDown(one, { key: "Enter" });
    expect(one).toHaveAttribute("aria-current", "true");
    fireEvent.keyDown(one, { key: "Escape" });
    expect(one).not.toHaveAttribute("aria-current");
  });
});

describe("bubble sides", () => {
  const side = (ref: string) => document.getElementById(ref)?.getAttribute("data-side");

  it("watches as the Seer by default, so nobody in the first lines is on the right", () => {
    open();
    expect(side("R1-1")).toBe("in");
    expect(side("R1-3")).toBe("in");
  });

  it("puts the player you choose to watch as on the right, without repeating their name", () => {
    open();
    menu();
    fireEvent.change(screen.getByLabelText("Watching as"), { target: { value: "Hal" } });
    expect(side("R1-1")).toBe("out");
    expect(side("R1-2")).toBe("in");
    expect(within(document.getElementById("R1-1") as HTMLElement).queryByText("Hal")).toBeNull();
  });

  it("can put everyone on the left", () => {
    open();
    menu();
    fireEvent.change(screen.getByLabelText("Watching as"), { target: { value: "Hal" } });
    fireEvent.click(screen.getByLabelText("Everyone on the left"));
    expect(side("R1-1")).toBe("in");
  });

  it("can put the wolves on the right, and then names the speaker on both sides", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Wolves on the right"));
    expect(side("R1-1")).toBe("out"); // Hal, a wolf
    expect(side("R1-3")).toBe("in"); // Ada, the Doctor
    expect(within(document.getElementById("R1-1") as HTMLElement).getByText("Hal")).toBeInTheDocument();
  });

  it("does not give the wolves away on the right while roles are hidden", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Wolves on the right"));
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    expect(side("R1-1")).toBe("in");
  });

  it("remembers the choice for the next visit", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Everyone on the left"));
    expect(localStorage.getItem("werewolf-coach.bubbles")).toBe("left");
  });

  it("starts a run of messages with a name and leaves the next one bare", () => {
    open();
    const fayOne = document.getElementById("R1-4") as HTMLElement;
    expect(fayOne).toHaveAttribute("data-first");
    expect(within(fayOne).getAllByText("Fay").length).toBeGreaterThan(0);
    // R1-5 is Cy straight after Fay: a new speaker, so it is the first of its own run
    expect(document.getElementById("R1-5")).toHaveAttribute("data-first");
  });
});
