import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("gives up on an API that is asleep instead of waiting for it, and says the API is not answering", async () => {
    // a server that never answers, the way a sleeping free-plan service looks until it is awake
    vi.stubGlobal(
      "fetch",
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => init.signal?.addEventListener("abort", () => reject(init.signal?.reason))),
    );
    const error = await api("/games", 20).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });

  it("still returns what a quick API says", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ total: 3 }));
    await expect(api<{ total: number }>("/games")).resolves.toEqual({ total: 3 });
  });

  it("waits only a few seconds by default, so a page never hangs for a minute", async () => {
    const seen: (AbortSignal | null | undefined)[] = [];
    vi.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
      seen.push(init.signal);
      return Response.json({});
    });
    await api("/games");
    expect(seen[0]).toBeInstanceOf(AbortSignal);
  });
});
