import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Replay } from "@/lib/api";
import { type BotNote, type Playable } from "@/lib/playback";
import { excerpt, welcomeNotes } from "@/lib/replay";
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
      {...props}
    />,
  );
}

// React only schedules the next message after rendering the last one, so step the clock in small bits
function wait(ms: number) {
  for (let t = 0; t < ms; t += 50) act(() => void vi.advanceTimersByTime(50));
}
const posted = () => document.querySelectorAll("[data-msg]").length;

beforeEach(() => {
  vi.useFakeTimers();
  window.location.hash = "";
});
afterEach(() => vi.useRealTimers());

describe("live replay", () => {
  it("starts with an empty chat and posts messages one at a time", () => {
    open();
    expect(posted()).toBe(0);
    expect(screen.getByText("0 of 14")).toBeInTheDocument();
    wait(3000);
    expect(screen.getByText(/ of 14$/).textContent).not.toBe("0 of 14");
    expect(screen.queryByText("14 of 14")).toBeNull();
  });

  it("shows who is typing just before their line arrives", () => {
    open({ entries: replay.entries.slice(4), players: replay.players });
    wait(450); // past the stage direction, into the wait for Hal's first line
    wait(450);
    expect(screen.getByRole("status")).toHaveTextContent("Hal is typing");
    wait(1500);
    expect(document.getElementById("R1-1")).toBeInTheDocument();
    expect(screen.queryByText(/Hal is typing/)).toBeNull();
  });

  it("pauses and carries on from the same place", () => {
    open();
    wait(2000);
    const at = screen.getByText(/ of 14$/).textContent;
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    wait(20_000);
    expect(screen.getByText(/ of 14$/).textContent).toBe(at);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    wait(2000);
    expect(screen.getByText(/ of 14$/).textContent).not.toBe(at);
  });

  it("shows the whole game at once on Instant", () => {
    open();
    fireEvent.click(screen.getByRole("radio", { name: "Instant" }));
    expect(screen.getByText("14 of 14")).toBeInTheDocument();
    expect(document.getElementById("R1-5")).toBeInTheDocument();
  });

  it("plays faster on Fast than on Slow", () => {
    const { unmount } = open();
    fireEvent.click(screen.getByRole("radio", { name: "Fast" }));
    wait(3000);
    const fast = posted();
    unmount();
    open();
    fireEvent.click(screen.getByRole("radio", { name: "Slow" }));
    wait(3000);
    expect(fast).toBeGreaterThan(posted());
  });

  it("offers to watch again at the end, and starts over from an empty chat", () => {
    open();
    wait(60_000);
    expect(screen.getByText("14 of 14")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Watch again" }));
    expect(posted()).toBe(0);
    expect(screen.getByText("0 of 14")).toBeInTheDocument();
  });

  it("skips private entries without waiting when roles are hidden", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "Chat options" }));
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    wait(50); // wolf chat, the night and the Seer's check are hidden: no pause for them
    expect(screen.queryByText(/only the wolves saw this/)).toBeNull();
    expect(screen.getByText(/ of 14$/).textContent).not.toBe("0 of 14");
  });

  it("opens a deep link with the whole game already there", () => {
    window.location.hash = "#R1-3";
    open();
    expect(posted()).toBe(5);
    expect(document.getElementById("R1-3")).toHaveAttribute("aria-current", "true");
  });
});

describe("the scrubber", () => {
  it("jumps to the point you drag to, and keeps what came before", () => {
    open();
    fireEvent.change(screen.getByRole("slider", { name: "Position in the game" }), { target: { value: "10" } });
    expect(screen.getByText("10 of 14")).toBeInTheDocument();
    expect(document.getElementById("R1-1")).toBeInTheDocument();
    expect(document.getElementById("R1-5")).toBeNull();
  });
});

describe("the welcome chat", () => {
  const note = (text: string): BotNote => ({ kind: "bot", text, round: 0 });
  const notes = welcomeNotes(replay.entries, "R1-1");
  const entries: Playable[] = [
    ...notes.before.map(note),
    ...excerpt(replay.entries, "R1-1"),
    ...notes.after.map(note),
  ];
  const welcome = () =>
    open({ entries, title: "Werewolf Coach", story: true, startAt: "R1-1", label: "Welcome chat" });

  it("starts with the bot typing a greeting before anyone else speaks", () => {
    welcome();
    wait(700);
    expect(screen.getByRole("status")).toHaveTextContent("Werewolf Coach is typing");
    wait(1000);
    expect(screen.getByText(/I'm the Werewolf Coach/)).toBeInTheDocument();
  });

  it("keeps the roles hidden until the featured message arrives, then reveals them", () => {
    welcome();
    wait(2500);
    expect(screen.queryByText("Werewolf")).toBeNull();
    wait(60_000);
    expect(screen.getAllByText("Werewolf").length).toBeGreaterThan(0);
    expect(document.getElementById("R1-1")).toHaveAttribute("aria-current", "true");
  });

  it("opens the featured message's thoughts inline, under the bubble, with no side panel", () => {
    welcome();
    wait(60_000);
    expect(screen.getByLabelText("Private thoughts of Hal")).toBeInTheDocument();
    expect(screen.queryByLabelText("Details")).toBeNull();
  });

  it("ends by pointing at what to do next and offers to watch again", () => {
    welcome();
    wait(60_000);
    expect(screen.getByText(/The chat is public, the thoughts are not/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Watch again" }));
    expect(screen.queryByText(/The chat is public/)).toBeNull();
  });
});
