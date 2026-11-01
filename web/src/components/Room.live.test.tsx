import { act, fireEvent, render, screen, within } from "@testing-library/react";
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

describe("a vote filling up", () => {
  const vote = (voter: string, target: string) =>
    ({
      kind: "vote",
      private: false,
      round: 1,
      voter,
      role: "Villager",
      team: "Village",
      target,
      reason: "A reason.",
      marks: [],
      subtext: null,
    }) as unknown as Playable;
  const entries: Playable[] = [vote("Cy", "Hal"), vote("Eve", "Hal"), vote("Gus", "Cy")];

  it("adds each voter to the poll as their vote comes in", () => {
    open({ entries });
    wait(900);
    expect(screen.getByText(/1 of 3 votes in/)).toBeInTheDocument();
    wait(5000);
    expect(screen.getByText(/3 votes\./)).toBeInTheDocument();
    expect(document.querySelectorAll("button[id^='vote-']")).toHaveLength(3);
  });

  it("says in the header that someone is voting, and shows no typing bubble for it", () => {
    open({ entries });
    wait(300);
    expect(screen.getByText(/voting…/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("the round picker", () => {
  // the same game told over two rounds: the first half in round 1, the rest in round 2
  const twoRounds = replay.entries.map((e, i) => ({ ...e, round: i < 7 ? 1 : 2 })) as Playable[];
  const picker = () => screen.getByRole("combobox", { name: "Jump to a round" });

  it("says which round the replay is in, and lists every round to jump to", () => {
    open({ entries: twoRounds });
    expect(picker()).toHaveValue("1");
    expect(within(picker()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Round 1 of 2", "Round 2 of 2"]);
    fireEvent.change(screen.getByRole("slider", { name: "Position in the game" }), { target: { value: "14" } });
    expect(picker()).toHaveValue("2");
  });

  it("jumps to the start of a round, with that round's first message showing", () => {
    open({ entries: twoRounds });
    fireEvent.change(picker(), { target: { value: "2" } });
    expect(document.getElementById("R1-2")).toBeInTheDocument(); // the first line of round 2
    expect(document.getElementById("R1-3")).toBeNull();
    expect(picker()).toHaveValue("2");
  });

  it("counts entries when the game is a single round, with nothing to pick", () => {
    open();
    expect(screen.getByText("0 of 14")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Jump to a round" })).toBeNull();
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

describe("a game that is still being played", () => {
  const room = (props: Partial<React.ComponentProps<typeof Room>> = {}) => (
    <Room
      entries={replay.entries.slice(0, 6)}
      players={replay.players}
      title="Play"
      avatar={<span />}
      label="Your game"
      {...props}
    />
  );

  it("is not finished when it has shown everything so far, and shows a typing bubble, not a notice", () => {
    render(room({ growing: true }));
    wait(15000);
    expect(screen.queryByRole("button", { name: "Watch again" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Hal is typing");
    expect(screen.queryByText(/Waiting for the next message/)).toBeNull();
  });

  it("holds the newest message back until the next one arrives, and names who is writing it", () => {
    const view = render(room({ growing: true }));
    wait(15000);
    expect(document.getElementById("R1-1")).toBeNull(); // Hal's line is the newest, so it waits
    expect(screen.getByText("Hal is typing…")).toBeInTheDocument(); // in the header too
    view.rerender(room({ growing: true, entries: replay.entries.slice(0, 8) }));
    wait(15000);
    expect(document.getElementById("R1-1")).toBeInTheDocument();
  });

  it("does not name anyone when the newest entry is not a message", () => {
    render(room({ growing: true, entries: replay.entries.slice(0, 5) }));
    wait(15000);
    expect(screen.getByRole("status")).toHaveTextContent("Someone is typing");
  });

  it("carries on with the entries that arrive later", () => {
    const view = render(room({ growing: true }));
    wait(15000);
    const before = posted();
    view.rerender(room({ growing: true, entries: replay.entries.slice(0, 12) }));
    wait(15000);
    expect(posted()).toBeGreaterThan(before);
    expect(screen.getByText(/ of 11$/)).toBeInTheDocument();
  });

  it("shows later entries at once when the reader has chosen Instant", () => {
    const view = render(room({ growing: true }));
    fireEvent.click(screen.getByRole("radio", { name: "Instant" }));
    const before = posted();
    view.rerender(room({ growing: true, entries: replay.entries.slice(0, 12) }));
    expect(screen.getByText("12 of 12")).toBeInTheDocument();
    expect(posted()).toBeGreaterThan(before);
  });

  it("is finished once nothing more is coming, and then shows what follows the game", () => {
    const end = <p>The end note</p>;
    const view = render(room({ growing: true, after: end }));
    wait(15000);
    expect(screen.queryByText("The end note")).toBeNull();
    view.rerender(room({ growing: false, after: end }));
    expect(screen.queryByText("The end note")).toBeNull(); // the held-back last message comes first
    wait(15000);
    expect(screen.getByRole("button", { name: "Watch again" })).toBeInTheDocument();
    expect(screen.getByText("The end note")).toBeInTheDocument();
  });
});
