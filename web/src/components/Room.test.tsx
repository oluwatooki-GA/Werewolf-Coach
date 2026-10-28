import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { Card, Replay, ReplayEntry, ReplayVote } from "@/lib/api";
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
const sides = () => fireEvent.click(screen.getByRole("button", { name: /^(You:|Sides:)/ }));

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
    expect(within(hal).getByText("Lie")).toBeInTheDocument();
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
    expect(within(hal).queryByText("Lie")).toBeNull();
    expect(hal).not.toHaveAttribute("data-lie");
    expect(screen.queryByText(/Only the wolves saw this/)).toBeNull();
    expect(panel().getByText(/Roles and private notes are hidden/)).toBeInTheDocument();
  });

  it("keeps tokens and tactics behind 'Show tactics'", () => {
    open();
    const hal = document.getElementById("R1-1") as HTMLElement;
    expect(within(hal).queryByText(/token/)).toBeNull();
    menu();
    fireEvent.click(screen.getByLabelText("Show tactics"));
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

  it("follows one player from their card: everyone else's messages dim, and it can be undone", () => {
    open();
    players();
    fireEvent.click(within(panel().getByLabelText("Players")).getByRole("button", { name: /Hal/ }));
    fireEvent.click(panel().getByRole("button", { name: "Show only Hal's messages" }));
    expect(document.getElementById("R1-2")).toHaveAttribute("data-dim");
    expect(document.getElementById("R1-1")).not.toHaveAttribute("data-dim");
    fireEvent.click(panel().getByRole("button", { name: "Show everyone again" }));
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
    sides();
    fireEvent.change(screen.getByLabelText("Watching as"), { target: { value: "Hal" } });
    expect(side("R1-1")).toBe("out");
    expect(side("R1-2")).toBe("in");
    expect(within(document.getElementById("R1-1") as HTMLElement).queryByText("Hal")).toBeNull();
  });

  it("can put everyone on the left", () => {
    open();
    sides();
    fireEvent.change(screen.getByLabelText("Watching as"), { target: { value: "Hal" } });
    fireEvent.click(screen.getByLabelText("Everyone on the left"));
    expect(side("R1-1")).toBe("in");
  });

  it("can put the wolves on the right, and then names the speaker on both sides", () => {
    open();
    sides();
    fireEvent.click(screen.getByLabelText("Wolves on the right"));
    expect(side("R1-1")).toBe("out"); // Hal, a wolf
    expect(side("R1-3")).toBe("in"); // Ada, the Doctor
    expect(within(document.getElementById("R1-1") as HTMLElement).getByText("Hal")).toBeInTheDocument();
  });

  it("puts the wolves on the right even while roles are hidden, and the explanation says it shows them", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    sides();
    fireEvent.click(screen.getByLabelText("Wolves on the right"));
    expect(side("R1-1")).toBe("out");
    expect(side("R1-3")).toBe("in");
    expect(screen.getByText(/This shows who the wolves are, even with roles hidden/)).toBeInTheDocument();
  });

  it("remembers the choice for the next visit", () => {
    open();
    sides();
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

describe("choosing your side", () => {
  it("shows who you are in the header without opening a menu", () => {
    open();
    expect(screen.getByRole("button", { name: "You: Di" })).toBeVisible();
  });

  it("says plainly that nobody is playing, and who you are", () => {
    open();
    sides();
    expect(screen.getByText(/No human is playing in a saved game\. You are Di/)).toBeInTheDocument();
  });

  it("updates the button when you pick another side", () => {
    open();
    sides();
    fireEvent.click(screen.getByLabelText("Wolves on the right"));
    expect(screen.getByRole("button", { name: "Sides: wolves right" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Everyone on the left"));
    expect(screen.getByRole("button", { name: "Sides: all left" })).toBeInTheDocument();
  });

  it("keeps the options menu for what to show, not for sides", () => {
    open();
    menu();
    expect(screen.getByLabelText("Roles and private notes")).toBeInTheDocument();
    expect(screen.queryByLabelText("Wolves on the right")).toBeNull();
  });
});

describe("Message info in plain words", () => {
  const info = () => {
    open();
    fireEvent.click(document.getElementById("R1-1") as HTMLElement);
    return panel();
  };

  it("says when the thinking happened, and whose note it is", () => {
    const view = info();
    expect(view.getByText("Before sending this message")).toBeInTheDocument();
    expect(view.getByRole("heading", { name: "Hal's private note" })).toBeInTheDocument();
  });

  const withBeliefs = (ref: string) =>
    replay.entries.map((e) =>
      e.kind === "line" && e.ref === ref && e.subtext
        ? {
            ...e,
            subtext: { ...e.subtext, beliefs: [{ player: "Eve", suspicion: 0.6, reason: "Vague in responses" }] },
          }
        : e,
    );

  it("explains a villager's suspicion bars and shows each as a percentage, not a bare decimal", () => {
    open({ entries: withBeliefs("R1-3") });
    fireEvent.click(document.getElementById("R1-3") as HTMLElement);
    const view = panel();
    expect(view.getByRole("heading", { name: "Who Ada thought was a wolf" })).toBeInTheDocument();
    expect(view.getByText(/The longer the bar, the more sure Ada was/)).toBeInTheDocument();
    expect(view.getByText("60%")).toBeInTheDocument();
    expect(view.queryByText("0.6")).toBeNull();
  });

  it("does not present a wolf's table as real suspicion, because a wolf knows who the wolves are", () => {
    open({ entries: withBeliefs("R1-1") });
    fireEvent.click(document.getElementById("R1-1") as HTMLElement);
    const view = panel();
    expect(view.queryByRole("heading", { name: "Who Hal thought was a wolf" })).toBeNull();
    expect(view.getByText("Hal is a wolf, so this is not a real suspicion list")).toBeInTheDocument();
    expect(view.getByText(/Wolves already know who the wolves are/)).toBeInTheDocument();
    expect(view.getByText("60%")).toBeInTheDocument(); // still there, for anyone who opens it
  });

  it("says what a bid and a move are, and names the lab's findings in words", () => {
    const view = info();
    expect(view.getByText(/Bid 3 tokens to speak next\. Plan: share info\./)).toBeInTheDocument();
    expect(view.getByRole("heading", { name: "Checked against the real roles" })).toBeInTheDocument();
    expect(view.getByText("Fake role claim")).toBeInTheDocument();
  });

  it("does not print a bare line number such as R1-2 on the bubble", () => {
    open();
    expect(document.getElementById("R1-2")?.textContent).not.toMatch(/R1-\d/);
  });

  it("says the role once, not once as a team and again as a role", () => {
    const view = info();
    expect(view.queryByText("Wolves")).toBeNull();
    expect(view.getAllByText("Werewolf")).toHaveLength(1);
  });
});

describe("the vote", () => {
  const vote = (voter: string, role: string, team: "Village" | "Wolves", target: string): ReplayVote =>
    ({
      kind: "vote",
      private: false,
      round: 1,
      voter,
      role,
      team,
      target,
      reason: `${voter} thinks ${target} is hiding something.`,
      marks: [],
      subtext: { note: `${voter} private note`, bid: null, intent: null, target, beliefs: [] },
    }) as ReplayVote;
  const withVotes = (): ReplayEntry[] => [
    ...replay.entries,
    vote("Cy", "Villager", "Village", "Hal"),
    vote("Eve", "Villager", "Village", "Hal"),
    vote("Hal", "Werewolf", "Wolves", "Cy"),
  ];

  it("shows the day's votes as one poll, not one message each", () => {
    open({ entries: withVotes() });
    const polls = screen.getAllByRole("region", { name: "Vote, round 1" });
    expect(polls).toHaveLength(1);
    expect(within(polls[0] as HTMLElement).getByText("Who should be voted out?")).toBeInTheDocument();
    expect(document.querySelectorAll("button[id^='vote-']")).toHaveLength(3);
    expect(document.querySelectorAll("article[id^='vote-']")).toHaveLength(0);
  });

  it("counts each option and says who voted that way", () => {
    open({ entries: withVotes() });
    const poll = within(screen.getByRole("region", { name: "Vote, round 1" }));
    const hal = poll.getByText("Hal", { selector: "span" }).closest("li") as HTMLElement;
    expect(within(hal).getByText("2")).toBeInTheDocument();
    expect(within(hal).getByRole("button", { name: /Cy voted for Hal/ })).toBeInTheDocument();
    expect(within(hal).getByRole("button", { name: /Eve voted for Hal/ })).toBeInTheDocument();
    expect(within(hal).getByText("Most votes")).toBeInTheDocument();
  });

  it("says tied, not most votes, when two players have the same number", () => {
    open({
      entries: [
        ...replay.entries,
        vote("Cy", "Villager", "Village", "Hal"),
        vote("Eve", "Villager", "Village", "Cy"),
      ],
    });
    expect(screen.getAllByText("Tied")).toHaveLength(2);
    expect(screen.queryByText("Most votes")).toBeNull();
  });

  it("opens why a player voted that way when you tap their name", () => {
    open({ entries: withVotes() });
    fireEvent.click(screen.getByRole("button", { name: /Cy voted for Hal/ }));
    expect(panel().getByText("Before voting")).toBeInTheDocument();
    expect(panel().getByRole("heading", { name: "What Cy said" })).toBeInTheDocument();
    expect(panel().getByText(/Cy thinks Hal is hiding something/)).toBeInTheDocument();
    expect(panel().getByText("Cy private note")).toBeInTheDocument();
  });
});

const fakeSeer = {
  id: "wolf.fake_seer",
  version: "2",
  role: "Werewolf",
  source: "General Mafia advice",
  summary: "Claim to be the Seer early.",
  instructions: "Say you are the Seer and name a villager as a wolf.",
  expected_moves: [],
  parent: null,
} as unknown as Card;

describe("a player's card", () => {
  const cards = { "wolf.fake_seer@2": fakeSeer };

  it("opens when you tap a player in the list, with the card's name and instructions", () => {
    open({ cards });
    players();
    fireEvent.click(within(panel().getByLabelText("Players")).getByRole("button", { name: /Hal/ }));
    const card = within(screen.getByRole("region", { name: "Hal, strategy" }));
    expect(card.getByText("fake seer")).toBeInTheDocument();
    expect(card.getByText("Say you are the Seer and name a villager as a wolf.")).toBeInTheDocument();
    expect(card.getByText(/General Mafia advice/)).toBeInTheDocument();
  });

  it("opens when you tap a name or an avatar in the chat", () => {
    open({ cards });
    fireEvent.click(within(document.getElementById("R1-1") as HTMLElement).getByRole("button", { name: "Hal: show their card" }));
    expect(screen.getByRole("region", { name: "Hal, strategy" })).toBeInTheDocument();
    expect(document.getElementById("R1-1")).not.toHaveAttribute("aria-current"); // tapping a person is not selecting the message
  });

  it("says so when a player had no card", () => {
    open({ cards });
    players();
    fireEvent.click(within(panel().getByLabelText("Players")).getByRole("button", { name: /Di/ }));
    expect(screen.getByText(/No strategy card\. Di played with the default instructions/)).toBeInTheDocument();
  });

  it("does not show a card, which would give the role away, while roles are hidden", () => {
    open({ cards });
    menu();
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    players();
    fireEvent.click(within(panel().getByLabelText("Players")).getByRole("button", { name: /Hal/ }));
    expect(screen.queryByText("fake seer")).toBeNull();
    expect(screen.getByText(/Roles and strategy cards are hidden/)).toBeInTheDocument();
  });

  it("goes back to the player list", () => {
    open({ cards });
    players();
    fireEvent.click(within(panel().getByLabelText("Players")).getByRole("button", { name: /Hal/ }));
    fireEvent.click(screen.getByRole("button", { name: "Back to the players" }));
    expect(panel().getByLabelText("Players")).toBeInTheDocument();
  });
});

describe("avatars", () => {
  const face = (ref: string) => within(document.getElementById(ref) as HTMLElement).getByRole("button", { name: /show their card/ });

  it("wear a wolf's head or a villager's bust once roles are shown", () => {
    open();
    expect(face("R1-1").querySelector("svg")).toBeTruthy(); // Hal, a wolf
    expect(face("R1-1")).not.toHaveTextContent("H");
    expect(face("R1-3").querySelector("svg")).toBeTruthy(); // Ada
    expect(face("R1-1").innerHTML).not.toBe(face("R1-3").innerHTML);
  });

  it("go back to the initial while roles are hidden, so they do not give the wolves away", () => {
    open();
    menu();
    fireEvent.click(screen.getByLabelText("Roles and private notes"));
    expect(face("R1-1").querySelector("svg")).toBeNull();
    expect(face("R1-1")).toHaveTextContent("H");
  });
});

describe("who is out", () => {
  it("marks a player as out in the list, with how and when", () => {
    open();
    players();
    expect(within(panel().getByLabelText("Players")).getByText("Killed in the night, round 1")).toBeInTheDocument();
  });
});

describe("what happened, in the chat", () => {
  it("gives the morning line a sun and the round a heading", () => {
    open();
    expect(screen.getByText(/^Morning:/).querySelector("svg")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Round 1" })).toBeInTheDocument();
  });
});
