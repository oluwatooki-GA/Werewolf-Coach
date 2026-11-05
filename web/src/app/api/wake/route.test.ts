import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

afterEach(() => vi.unstubAllGlobals());

describe("GET /api/wake", () => {
  it("says the API is up when its health check answers", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ status: "ok" }));
    const response = await GET();
    expect(await response.json()).toEqual({ up: true });
  });

  it("says it is not up when the health check fails, and still answers quickly", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("connection refused");
    });
    expect(await (await GET()).json()).toEqual({ up: false });
  });

  it("says it is not up when the database is down (a 503)", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ status: "down" }, { status: 503 }));
    expect(await (await GET()).json()).toEqual({ up: false });
  });

  it("is never cached, since the answer changes the moment the API wakes", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ status: "ok" }));
    expect((await GET()).headers.get("cache-control")).toContain("no-store");
  });
});
