import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Card, PlayStatus, PlayTable, Replay } from "@/lib/api";
import fixture from "../test/replay.fixture.json";

const refresh = vi.fn();
const router = { refresh }; // one object, as the real router is, so effects that depend on it do not restart
vi.mock("next/navigation", () => ({ useRouter: () => router }));

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

const DEFAULT_TEXT = "Play to win for your team.";
const seat = (name: string, role: string) => ({ name, role });
const table: PlayTable = {
  seed: 3,
  default_card: DEFAULT_TEXT,
  seats: [
    seat("Ada", "Werewolf"),
    seat("Bo", "Villager"),
    seat("Cy", "Seer"),
    seat("Di", "Doctor"),
    seat("Eve", "Villager"),
    seat("Fay", "Werewolf"),
    seat("Gus", "Villager"),
    seat("Hal", "Villager"),
  ],
};
const PLAYERS = table.seats.map((s) => s.name);

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const calls = () => fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit | undefined)?.method ?? "GET"]);

beforeEach(() => {
  refresh.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function show(status: PlayStatus = open) {
  return render(<PlayBoard cards={cards} status={status} table={table} />);
}

const player = (name: string) => within(screen.getByRole("radiogroup", { name }));
const pick = (name: string, card: string) => fireEvent.click(player(name).getByRole("radio", { name: card }));
const start = () => screen.getByRole("button", { name: "Start the game" });
const shuffle = () => screen.getByRole("button", { name: "Shuffle seats" });
const names = (p: string) => player(p).getAllByRole("radio").map((r) => r.getAttribute("aria-label"));

async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("picking cards", () => {
  it("asks for a card for each of the eight players, one by one", () => {
    show();
    for (const name of PLAYERS) expect(screen.getByRole("radiogroup", { name })).toBeInTheDocument();
    expect(screen.getAllByRole("radiogroup")).toHaveLength(8);
  });

  it("groups the players by role and says each player's role", () => {
    show();
    for (const name of ["Wolves", "Villagers", "Seer", "Doctor"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.getAllByText("Werewolf")).toHaveLength(2);
    expect(screen.getAllByText("Villager")).toHaveLength(4);
  });

  it("offers only the cards that fit each player's role, with Default always first", () => {
    show();
    expect(names("Ada")).toEqual(["Default", "lie low", "accuse early"]);
    expect(names("Bo")).toEqual(["Default", "track votes"]);
    expect(names("Cy")).toEqual(["Default", "reveal now"]);
    expect(names("Di")).toEqual(["Default", "protect seer"]);
  });

  it("starts with Default chosen for every player", () => {
    show();
    for (const name of PLAYERS) expect(player(name).getByRole("radio", { name: "Default" })).toBeChecked();
  });

  it("choosing a card moves that player's choice and shows what the card says", () => {
    show();
    pick("Ada", "lie low");
    expect(player("Ada").getByRole("radio", { name: "lie low" })).toBeChecked();
    expect(player("Ada").getByRole("radio", { name: "Default" })).not.toBeChecked();
    expect(screen.getByText("Instructions for wolf.lie_low.")).toBeInTheDocument();
  });

  it("lets two players on the same side play different cards", () => {
    show();
    pick("Ada", "lie low");
    pick("Fay", "accuse early");
    expect(player("Ada").getByRole("radio", { name: "lie low" })).toBeChecked();
    expect(player("Fay").getByRole("radio", { name: "accuse early" })).toBeChecked();
    expect(player("Fay").getByRole("radio", { name: "lie low" })).not.toBeChecked();
  });

  it("keeps every pick when several are made at once, not only the last", () => {
    show();
    act(() => {
      pick("Ada", "lie low");
      pick("Cy", "reveal now");
      pick("Bo", "track votes");
    });
    expect(player("Ada").getByRole("radio", { name: "lie low" })).toBeChecked();
    expect(player("Cy").getByRole("radio", { name: "reveal now" })).toBeChecked();
    expect(player("Bo").getByRole("radio", { name: "track votes" })).toBeChecked();
  });

  it("can give one card to every player on a side at once, and then change one of them", () => {
    show();
    const all = screen.getByRole("combobox", { name: "Same card for all Villagers" });
    fireEvent.change(all, { target: { value: "villager.track_votes@2" } });
    for (const name of ["Bo", "Eve", "Gus", "Hal"]) {
      expect(player(name).getByRole("radio", { name: "track votes" })).toBeChecked();
    }
    expect(player("Ada").getByRole("radio", { name: "Default" })).toBeChecked(); // other sides untouched
    pick("Eve", "Default");
    expect(player("Eve").getByRole("radio", { name: "Default" })).toBeChecked();
    expect(player("Bo").getByRole("radio", { name: "track votes" })).toBeChecked();
  });

  it("offers the same-card shortcut only to sides with more than one player", () => {
    show();
    expect(screen.getByRole("combobox", { name: "Same card for all Wolves" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Same card for all Villagers" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /Seer/ })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /Doctor/ })).toBeNull();
  });

  it("shows what the default card says for every player left on Default", () => {
    show();
    expect(screen.getAllByText(DEFAULT_TEXT)).toHaveLength(8);
    pick("Ada", "lie low");
    expect(screen.getAllByText(DEFAULT_TEXT)).toHaveLength(7);
    expect(screen.getByText("Instructions for wolf.lie_low.")).toBeInTheDocument();
  });

  it("explains what Default means", () => {
    show();
    expect(screen.getAllByText(/standard instructions/i).length).toBeGreaterThan(0);
  });
});

describe("dealing new seats", () => {
  const next: PlayTable = {
    seed: 77,
    default_card: DEFAULT_TEXT,
    seats: [
      seat("Ada", "Villager"),
      seat("Bo", "Werewolf"),
      seat("Cy", "Villager"),
      seat("Di", "Seer"),
      seat("Eve", "Doctor"),
      seat("Fay", "Villager"),
      seat("Gus", "Werewolf"),
      seat("Hal", "Villager"),
    ],
  };

  it("asks for a new table and shows the new roles, with every choice back to Default", async () => {
    fetchMock.mockResolvedValue(json(next));
    show();
    pick("Ada", "lie low");
    await act(async () => fireEvent.click(shuffle()));
    expect(calls()).toEqual([["/api/play/table", "GET"]]);
    expect(names("Ada")).toEqual(["Default", "track votes"]);
    expect(names("Bo")).toEqual(["Default", "lie low", "accuse early"]);
    for (const name of PLAYERS) expect(player(name).getByRole("radio", { name: "Default" })).toBeChecked();
  });

  it("plays the table that is shown: the new seed goes with the cards", async () => {
    fetchMock.mockResolvedValueOnce(json(next)).mockResolvedValue(json({ id: GAME }, 202));
    show();
    await act(async () => fireEvent.click(shuffle()));
    await act(async () => fireEvent.click(start()));
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(init.body as string).seed).toBe(77);
  });

  it("keeps the table and the picks when a new table cannot be fetched, and says so", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    show();
    pick("Ada", "lie low");
    await act(async () => fireEvent.click(shuffle()));
    expect(screen.getByText(/could not deal new seats/i)).toBeInTheDocument();
    expect(player("Ada").getByRole("radio", { name: "lie low" })).toBeChecked();
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
    pick("Ada", "lie low");
    expect(screen.getByText("Instructions for wolf.lie_low.")).toBeInTheDocument();
  });
});

describe("starting a game", () => {
  const picked = () => {
    show();
    pick("Ada", "lie low");
    pick("Fay", "accuse early");
    pick("Cy", "reveal now");
  };

  it("sends the seed and a choice for every player, Default as the word default", async () => {
    fetchMock.mockResolvedValue(json({ id: GAME }, 202));
    picked();
    await act(async () => fireEvent.click(start()));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/play");
    expect(JSON.parse(init.body as string)).toEqual({
      seed: 3,
      cards: {
        Ada: "wolf.lie_low@1",
        Bo: "default",
        Cy: "seer.reveal_now@3",
        Di: "default",
        Eve: "default",
        Fay: "wolf.accuse_early@2",
        Gus: "default",
        Hal: "default",
      },
    });
  });

  it("shows the refusal when the start is refused, and lets you press it again", async () => {
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
});

describe("watching the game as it is played", () => {
  const replay = fixture as unknown as Replay;
  const seats = replay.players.map((p) => ({ name: p.name, role: p.role }));
  const wolf = replay.players.find((p) => p.role === "Werewolf")?.name ?? "";
  const entries = replay.entries;
  const page = (status: string, total: number, part: unknown[], extra: object = {}) => ({
    status,
    game_id: null,
    reason: null,
    total,
    entries: part,
    ...extra,
  });
  const running = (to: number, from = 0) => page("running", to, entries.slice(from, to));
  const finished = page("finished", entries.length, entries.slice(10), { game_id: "1-abcd1234" });

  /** A server that answers each look at the game with the next page. */
  function serve(pages: unknown[]) {
    let n = 0;
    fetchMock.mockImplementation(async (url: string) =>
      url === "/api/play" ? json({ id: GAME }, 202) : json(pages[Math.min(n++, pages.length - 1)]),
    );
  }

  async function begin() {
    render(<PlayBoard cards={cards} status={open} table={{ seed: 1, default_card: DEFAULT_TEXT, seats }} />);
    fireEvent.click(within(screen.getByRole("radiogroup", { name: wolf })).getByRole("radio", { name: "lie low" }));
    await act(async () => fireEvent.click(start()));
  }
  const looks = () => calls().filter(([, method]) => method === "GET").map(([url]) => url);
  const instant = () => fireEvent.click(screen.getByRole("radio", { name: "Instant" }));

  it("swaps the picker for the game, which cannot be started twice", async () => {
    serve([running(4)]);
    await begin();
    expect(screen.getByRole("feed")).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: wolf })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start the game" })).toBeNull();
  });

  it("asks from the first entry, and each time from the entries it already has", async () => {
    serve([running(4), running(10, 4), finished]);
    await begin();
    await tick(1100);
    await tick(1100);
    expect(looks()).toEqual([
      `/api/play/${GAME}/live?after=0`,
      `/api/play/${GAME}/live?after=4`,
      `/api/play/${GAME}/live?after=10`,
    ]);
  });

  it("shows the whole game, in order and once, and then links to the full replay", async () => {
    serve([running(4), running(10, 4), finished]);
    await begin();
    instant();
    await tick(1100);
    await tick(1100);
    expect(screen.getByText(`${entries.length} of ${entries.length}`)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Watch the full replay" });
    expect(link).toHaveAttribute("href", "/games/1-abcd1234");
    expect(refresh).toHaveBeenCalledTimes(1); // so the games left today and the list are read again
  });

  it("shows a typing bubble while the game goes on, and has no link yet", async () => {
    serve([running(4), page("running", 4, [])]); // then nothing new, as a real server would say
    await begin();
    for (let i = 0; i < 150; i++) await tick(100); // in small steps: each message waits for a render
    expect(screen.getByRole("status")).toHaveTextContent(/ is typing$/);
    expect(screen.queryByRole("link", { name: "Watch the full replay" })).toBeNull();
  });

  it("stops asking once the game is over", async () => {
    serve([running(4), finished]);
    await begin();
    await tick(1100);
    const after = fetchMock.mock.calls.length;
    await tick(10_000);
    expect(fetchMock.mock.calls.length).toBe(after);
  });

  it("keeps what was played, says why a game stopped, and lets you try again with your picks", async () => {
    serve([running(4), page("stopped", 4, [], { reason: "most answers failed" })]);
    await begin();
    instant();
    await tick(1100);
    expect(screen.getByText(/most answers failed/)).toBeInTheDocument();
    expect(screen.getByText("4 of 4")).toBeInTheDocument(); // what was played stays
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(start()).toBeEnabled();
    expect(within(screen.getByRole("radiogroup", { name: wolf })).getByRole("radio", { name: "lie low" })).toBeChecked();
    await act(async () => fireEvent.click(start()));
    expect(looks().at(-1)).toBe(`/api/play/${GAME}/live?after=0`); // a new game starts from the first entry
  });

  it("tries a failed look again, and carries on", async () => {
    let n = 0;
    fetchMock.mockImplementation(async (url: string) => {
      if (url === "/api/play") return json({ id: GAME }, 202);
      n += 1;
      if (n === 1) throw new Error("blip");
      return json(n === 2 ? running(4) : finished);
    });
    await begin();
    instant();
    await tick(1100);
    await tick(1100);
    expect(screen.getByRole("link", { name: "Watch the full replay" })).toBeInTheDocument();
  });

  it("gives up after five failed looks in a row, and says the game goes on without it", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === "/api/play") return json({ id: GAME }, 202);
      throw new Error("offline");
    });
    await begin();
    for (let i = 0; i < 6; i++) await tick(1100);
    expect(screen.getByText(/lost the connection/i)).toBeInTheDocument();
    const after = fetchMock.mock.calls.length;
    await tick(10_000);
    expect(fetchMock.mock.calls.length).toBe(after);
  });
});
