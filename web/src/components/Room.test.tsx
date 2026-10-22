import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
      topic="A recorded game"
      label="A recorded game"
      {...props}
    />,
  );
}

const panel = () => within(screen.getByLabelText("Details"));

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

  it("shows a message's private note in the side panel when you click it", () => {
    open();
    expect(panel().getByText(/Select a message/)).toBeInTheDocument();
    fireEvent.click(document.getElementById("R1-1") as HTMLElement);
    expect(panel().getByText("Claimed Seer to gain trust and deflect suspicion.")).toBeInTheDocument();
    expect(panel().getByText(/the claimed check does not match the log/i)).toBeInTheDocument();
    expect(document.getElementById("R1-1")).toHaveAttribute("aria-current", "true");
  });

  it("opens with a chosen message already selected", () => {
    open({ startAt: "R1-2" });
    expect(document.getElementById("R1-2")).toHaveAttribute("aria-current", "true");
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

  it("shows a cited line as a reply above the message that cites it", () => {
    open();
    const fay = document.getElementById("R1-2") as HTMLElement;
    const reply = fay.querySelector("a[href='#R1-1']");
    expect(reply).toHaveTextContent("Hal");
    expect(reply).toHaveTextContent("I am the Seer");
  });

  it("shows the wolf chat and the night as private, marked as such", () => {
    open();
    expect(screen.getAllByText(/only the wolves saw this/)).toHaveLength(2);
    expect(screen.getByText(/The wolves chose Eve/)).toBeInTheDocument();
  });

  it("hides roles, the lab's findings, wolf chat and private notes in the public view", () => {
    open();
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(within(hal).queryByText("Werewolf")).toBeNull();
    expect(within(hal).queryByText("lie")).toBeNull();
    expect(hal).not.toHaveAttribute("data-lie");
    expect(screen.queryByText(/only the wolves saw this/)).toBeNull();
    expect(panel().getByText(/Roles and private notes are hidden/)).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: /Players, 8 players/ }).length).toBeGreaterThan(0);
  });

  it("groups the member list by team", () => {
    open();
    const members = panel().getByLabelText("Players");
    expect(within(members).getByRole("heading", { name: "Wolves, 2 players" })).toBeInTheDocument();
    expect(within(members).getByRole("heading", { name: "Village, 6 players" })).toBeInTheDocument();
  });

  it("follows one player: everyone else's messages dim, and clicking again clears it", () => {
    open();
    const members = panel().getByLabelText("Players");
    const hal = within(members).getByRole("button", { name: /Hal/ });
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

  it("is an excerpt with no header, no dividers and no member list when compact", () => {
    open({ compact: true, title: undefined, topic: undefined, startAt: "R1-1" });
    expect(screen.queryByRole("heading", { name: "Round 1" })).toBeNull();
    expect(screen.queryByLabelText("Players")).toBeNull();
    expect(panel().getByLabelText("Private thoughts of Hal")).toBeInTheDocument();
  });
});
