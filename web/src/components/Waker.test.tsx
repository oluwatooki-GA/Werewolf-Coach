import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { Waker } from "./Waker";

const answers = (...ups: boolean[]) => {
  const queue = [...ups];
  const fetcher = vi.fn<(url: string) => Promise<Response>>(async () =>
    Response.json({ up: queue.length > 1 ? queue.shift() : queue[0] }),
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
};

// advance in small steps: each poll waits for the one before it to render
const wait = async (ms: number) => {
  for (let t = 0; t < ms; t += 500) await act(async () => void vi.advanceTimersByTime(500));
};

beforeEach(() => {
  vi.useFakeTimers();
  refresh.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Waker", () => {
  it("tells the visitor the API is waking up and that it takes up to a minute", () => {
    answers(false);
    render(<Waker />);
    expect(screen.getByRole("status")).toHaveTextContent(/waking up/i);
    expect(screen.getByRole("status")).toHaveTextContent(/a minute/i);
  });

  it("asks the site every few seconds, and does not reload the page while the API is still asleep", async () => {
    const fetcher = answers(false);
    render(<Waker />);
    await wait(10_000);
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(fetcher.mock.calls.every(([url]) => url === "/api/wake")).toBe(true);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes the page once the API answers, and then stops asking", async () => {
    const fetcher = answers(false, false, true);
    render(<Waker />);
    await wait(15_000);
    expect(refresh).toHaveBeenCalledTimes(1);
    const calls = fetcher.mock.calls.length;
    await wait(15_000);
    expect(fetcher.mock.calls.length).toBe(calls);
  });

  it("does what it is told instead of refreshing when it is given something else to do", async () => {
    answers(true);
    const onUp = vi.fn();
    render(<Waker onUp={onUp} />);
    await wait(5_000);
    expect(onUp).toHaveBeenCalledTimes(1);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("keeps asking when the site itself cannot be reached", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("offline");
    });
    render(<Waker />);
    await wait(10_000);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/waking up/i);
  });

  it("admits it when the API has not answered after two minutes", async () => {
    answers(false);
    render(<Waker />);
    await wait(125_000);
    expect(screen.getByRole("status")).toHaveTextContent(/still not answering/i);
  });

  it("stops asking when it is taken off the page", async () => {
    const fetcher = answers(false);
    const view = render(<Waker />);
    await wait(4_000);
    view.unmount();
    const calls = fetcher.mock.calls.length;
    await wait(20_000);
    expect(fetcher.mock.calls.length).toBe(calls);
  });
});
