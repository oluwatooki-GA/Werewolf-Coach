import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Card, PlayStatus } from "@/lib/api";
import { PlayBoard } from "./PlayBoard";

const card = (id: string, version: string, role: string, summary: string) =>
  ({
    id,
    version,
    role,
    source: `Source of ${id}`,
    summary,
    instructions: `Instructions for ${id}.`,
    expected_moves: [],
    parent: null,
  }) as unknown as Card;

const cards = [
  card("wolf.lie_low", "1", "Werewolf", "Stay unnoticed."),
  card("wolf.accuse_early", "2", "Werewolf", "Accuse early."),
  card("villager.track_votes", "2", "Villager", "Track who changes votes."),
  card("seer.reveal_now", "3", "Seer", "Reveal right away."),
  card("doctor.protect_seer", "2", "Doctor", "Protect the Seer."),
];

const open: PlayStatus = { available: true, reason: "", games_left: 3 };
const GAME = "0123456789abcdef0123456789abcdef";

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const calls = () => fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit | undefined)?.method ?? "GET"]);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function show(status: PlayStatus = open) {
  return render(<PlayBoard cards={cards} status={status} />);
}

const group = (name: string) => within(screen.getByRole("radiogroup", { name }));
const start = () => screen.getByRole("button", { name: "Start the game" });

async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("picking cards", () => {
  it("asks for a card for each of the four sides", () => {
    show();
    for (const name of ["Wolves", "Villagers", "Seer", "Doctor"]) {
      expect(screen.getByRole("radiogroup", { name })).toBeInTheDocument();
    }
  });

  it("offers only the cards that fit each role, with Default always first", () => {
    show();
    const names = (g: string) => group(g).getAllByRole("radio").map((r) => r.getAttribute("aria-label"));
    expect(names("Wolves")).toEqual(["Default", "lie low", "accuse early"]);
    expect(names("Villagers")).toEqual(["Default", "track votes"]);
    expect(names("Seer")).toEqual(["Default", "reveal now"]);
    expect(names("Doctor")).toEqual(["Default", "protect seer"]);
  });

  it("starts with Default chosen for every side", () => {
    show();
    for (const name of ["Wolves", "Villagers", "Seer", "Doctor"]) {
      expect(group(name).getByRole("radio", { name: "Default" })).toBeChecked();
    }
  });

  it("choosing a card moves the choice and shows what the card says", () => {
    show();
    fireEvent.click(group("Wolves").getByRole("radio", { name: "lie low" }));
    expect(group("Wolves").getByRole("radio", { name: "lie low" })).toBeChecked();
    expect(group("Wolves").getByRole("radio", { name: "Default" })).not.toBeChecked();
    expect(screen.getByText("Instructions for wolf.lie_low.")).toBeInTheDocument();
  });

  it("keeps every pick when several are made at once, not only the last", () => {
    show();
    act(() => {
      fireEvent.click(group("Wolves").getByRole("radio", { name: "lie low" }));
      fireEvent.click(group("Seer").getByRole("radio", { name: "reveal now" }));
      fireEvent.click(group("Villagers").getByRole("radio", { name: "track votes" }));
    });
    expect(group("Wolves").getByRole("radio", { name: "lie low" })).toBeChecked();
    expect(group("Seer").getByRole("radio", { name: "reveal now" })).toBeChecked();
    expect(group("Villagers").getByRole("radio", { name: "track votes" })).toBeChecked();
  });

  it("explains what Default means", () => {
    show();
    expect(screen.getAllByText(/standard instructions/i).length).toBeGreaterThan(0);
  });
});

describe("the status", () => {
  it("says how many games are left today", () => {
    show();
    expect(screen.getByText(/3 games left today/)).toBeInTheDocument();
  });

  it("says one game, not 1 games", () => {
    show({ ...open, games_left: 1 });
    expect(screen.getByText(/1 game left today/)).toBeInTheDocument();
  });

  it("when play is paused, says why and turns the button off, but cards can still be browsed", () => {
    show({ available: false, reason: "Today's play budget is used up. Play opens again tomorrow.", games_left: 0 });
    expect(screen.getByText(/Play opens again tomorrow/)).toBeInTheDocument();
    expect(start()).toBeDisabled();
    fireEvent.click(group("Wolves").getByRole("radio", { name: "lie low" }));
    expect(screen.getByText("Instructions for wolf.lie_low.")).toBeInTheDocument();
  });
});

describe("starting a game", () => {
  const picked = () => {
    show();
    fireEvent.click(group("Wolves").getByRole("radio", { name: "lie low" }));
    fireEvent.click(group("Seer").getByRole("radio", { name: "reveal now" }));
  };

  it("sends the four choices, and Default as the word default", async () => {
    fetchMock.mockResolvedValue(json({ id: GAME }, 202));
    picked();
    await act(async () => fireEvent.click(start()));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/play");
    expect(JSON.parse(init.body as string)).toEqual({
      wolf: "wolf.lie_low@1",
      villager: "default",
      seer: "seer.reveal_now@3",
      doctor: "default",
    });
  });

  it("shows the agents playing, with a typing indicator, and cannot be started twice", async () => {
    fetchMock.mockResolvedValue(json({ id: GAME }, 202));
    picked();
    await act(async () => fireEvent.click(start()));
    expect(screen.getByText(/The agents are playing/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("is typing");
    expect(screen.queryByRole("button", { name: "Start the game" })).toBeNull();
  });

  it("polls, and when the game is finished links to its replay", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url === "/api/play"
        ? json({ id: GAME }, 202)
        : json({ id: GAME, status: fetchMock.mock.calls.length > 3 ? "finished" : "running", game_id: "1-abcd1234", reason: null }),
    );
    picked();
    await act(async () => fireEvent.click(start()));
    await tick(2100);
    await tick(2100);
    await tick(2100);
    const link = screen.getByRole("link", { name: "Watch the game" });
    expect(link).toHaveAttribute("href", "/games/1-abcd1234");
    expect(screen.queryByRole("status")).toBeNull();
    expect(calls().filter(([, method]) => method === "GET").every(([url]) => url === `/api/play/${GAME}`)).toBe(true);
  });

  it("says why a game stopped, and lets you try again", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url === "/api/play"
        ? json({ id: GAME }, 202)
        : json({ id: GAME, status: "stopped", game_id: null, reason: "most answers failed" }),
    );
    picked();
    await act(async () => fireEvent.click(start()));
    await tick(2100);
    expect(screen.getByText(/most answers failed/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(start()).toBeEnabled();
    expect(group("Wolves").getByRole("radio", { name: "lie low" })).toBeChecked(); // your picks are kept
  });

  it("shows the reason when the start is refused, and lets you press it again", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Too many requests. Wait a minute and try again." }, 429));
    picked();
    await act(async () => fireEvent.click(start()));
    expect(screen.getByText(/Too many requests/)).toBeInTheDocument();
    expect(start()).toBeEnabled();
  });

  it("copes with the site not reaching the server at all", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    picked();
    await act(async () => fireEvent.click(start()));
    expect(screen.getByText(/could not reach the game server/i)).toBeInTheDocument();
    expect(start()).toBeEnabled();
  });

  it("stops asking once the game is over", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url === "/api/play" ? json({ id: GAME }, 202) : json({ id: GAME, status: "finished", game_id: "1-x", reason: null }),
    );
    picked();
    await act(async () => fireEvent.click(start()));
    await tick(2100);
    const after = fetchMock.mock.calls.length;
    await tick(10_000);
    expect(fetchMock.mock.calls.length).toBe(after);
  });
});
