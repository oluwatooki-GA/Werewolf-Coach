import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AdminOverview } from "@/lib/api";
import { AdminBoard } from "./AdminBoard";

const overview: AdminOverview = {
  metrics: {
    games: { total: 150, by_status: { finished: 148, stopped: 2 }, by_source: { play: 4 }, unclean: 3 },
    play: { started: 5, finished: 3, stopped: 1, running: 1 },
    spend: { today: 0.3, total: 0.55, by_day: { "2026-10-28": 0.25, "2026-10-29": 0.3 } },
  },
  recent: [
    { id: "p1", status: "finished", reason: "", cost: 0.11, created_at: 1_790_000_000, game_id: "5-abcd1234" },
    { id: "p2", status: "stopped", reason: "most answers failed", cost: 0, created_at: 1_789_999_000, game_id: null },
  ],
  active_games: 1,
  play_model: "gpt-4o-mini",
};

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

async function signIn(token = "s3cret") {
  render(<AdminBoard />);
  fireEvent.change(screen.getByLabelText("Admin token"), { target: { value: token } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Open" })));
}

describe("the admin page", () => {
  it("asks for the token first and shows nothing else", () => {
    render(<AdminBoard />);
    expect(screen.getByLabelText("Admin token")).toHaveAttribute("type", "password");
    expect(screen.queryByText(/Games played here/)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the token as a bearer header to the site's own route, never in the address", async () => {
    fetchMock.mockResolvedValue(json(overview));
    await signIn("s3cret");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/admin");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer s3cret");
  });

  it("shows the counts, the spend and the latest games once the token is accepted", async () => {
    fetchMock.mockResolvedValue(json(overview));
    await signIn();
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
    const played = within(screen.getByRole("region", { name: "Games played here" }));
    expect(played.getByText("Started").nextSibling).toHaveTextContent("5");
    expect(played.getByText("Running now").nextSibling).toHaveTextContent("1");
    const spend = within(screen.getByRole("region", { name: "Spend" }));
    expect(spend.getByText("Today").nextSibling).toHaveTextContent("$0.30");
    expect(spend.getByText("In all").nextSibling).toHaveTextContent("$0.55");
    expect(screen.getByText("2026-10-28")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "5-abcd1234" })).toHaveAttribute("href", "/games/5-abcd1234");
    expect(screen.getByText(/most answers failed/)).toBeInTheDocument();
  });

  it("says the token was not accepted, and lets you try again", async () => {
    fetchMock.mockResolvedValue(json({ detail: "A valid admin token is needed." }, 401));
    await signIn("nope");
    expect(screen.getByRole("alert")).toHaveTextContent("That token was not accepted.");
    expect(screen.getByLabelText("Admin token")).toBeInTheDocument();
  });

  it("says plainly when the admin page is not turned on", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Not Found" }, 404));
    await signIn();
    expect(screen.getByRole("alert")).toHaveTextContent(/not turned on/i);
  });

  it("copes with the server not answering", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    await signIn();
    expect(screen.getByRole("alert")).toHaveTextContent(/could not reach/i);
  });

  it("does not keep the token once it has been used", async () => {
    fetchMock.mockResolvedValue(json(overview));
    await signIn("s3cret");
    expect(document.body.innerHTML).not.toContain("s3cret");
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });
});
