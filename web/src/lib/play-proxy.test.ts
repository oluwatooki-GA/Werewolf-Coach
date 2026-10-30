import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forwardToApi, isPlayId, livePath, tablePath } from "./play-proxy";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_URL", "http://api.test:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const asked = (body = "", headers: Record<string, string> = {}) =>
  new Request("http://site.test/api/play", { method: "POST", body, headers });

describe("forwardToApi", () => {
  it("passes a start request to the API with its body and the visitor's address", async () => {
    fetchMock.mockResolvedValue(new Response('{"id":"abc"}', { status: 202 }));
    const response = await forwardToApi("/play", asked('{"wolf":"default"}', { "x-forwarded-for": "203.0.113.7" }), "POST");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test:8000/play");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"wolf":"default"}');
    expect(new Headers(init.headers).get("x-forwarded-for")).toBe("203.0.113.7");
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ id: "abc" });
  });

  it("keeps the API's status and message, such as a refused card or a paused game", async () => {
    fetchMock.mockResolvedValue(new Response('{"detail":"Play mode is paused."}', { status: 503 }));
    const response = await forwardToApi("/play", asked("{}"), "POST");
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ detail: "Play mode is paused." });
  });

  it("reads a game's state with a GET and no body", async () => {
    fetchMock.mockResolvedValue(new Response('{"status":"running"}', { status: 200 }));
    const request = new Request("http://site.test/api/play/abc", { method: "GET" });
    await forwardToApi("/play/abc", request, "GET");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("passes on the extra headers it is given, such as the admin token", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    await forwardToApi("/admin/overview", asked("{}"), "GET", { authorization: "Bearer abc" });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer abc");
  });

  it("says so plainly when the API is not answering", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));
    const response = await forwardToApi("/play", asked("{}"), "POST");
    expect(response.status).toBe(502);
    expect((await response.json()).detail).toMatch(/not answering/);
  });

  it("sends no address header when the visitor's address is unknown", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    await forwardToApi("/play", asked("{}"), "POST");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).has("x-forwarded-for")).toBe(false);
  });
});

describe("isPlayId", () => {
  it("accepts the 32 hex characters a game id is made of", () => {
    expect(isPlayId("0123456789abcdef0123456789abcdef")).toBe(true);
  });

  it("refuses anything that could reach another route", () => {
    for (const bad of ["", "status", "../games", "abc/def", "0123456789abcdef0123456789abcde", "ZZZZ456789abcdef0123456789abcdef"]) {
      expect(isPlayId(bad)).toBe(false);
    }
  });
});

describe("tablePath", () => {
  it("asks for a new table when no seed is given", () => {
    expect(tablePath("http://site.test/api/play/table")).toBe("/play/table");
  });

  it("passes a seed on when it is a whole number of up to six digits", () => {
    expect(tablePath("http://site.test/api/play/table?seed=77")).toBe("/play/table?seed=77");
  });

  it("drops anything else, so nothing but a seed can reach the API", () => {
    for (const bad of ["x", "-1", "1.5", "1234567", "7&model=opus", "../games"]) {
      expect(tablePath(`http://site.test/api/play/table?seed=${encodeURIComponent(bad)}`)).toBe("/play/table");
    }
  });
});

describe("livePath", () => {
  const ID = "0123456789abcdef0123456789abcdef";

  it("asks for a game from the start when no point is given", () => {
    expect(livePath(ID, `http://site.test/api/play/${ID}/live`)).toBe(`/play/${ID}/live`);
  });

  it("passes on the point to read from when it is a whole number", () => {
    expect(livePath(ID, `http://site.test/api/play/${ID}/live?after=12`)).toBe(`/play/${ID}/live?after=12`);
  });

  it("drops anything else, so nothing but that number can reach the API", () => {
    for (const bad of ["x", "-1", "1.5", "1234567", "3&model=opus", "../games"]) {
      expect(livePath(ID, `http://site.test/api/play/${ID}/live?after=${encodeURIComponent(bad)}`)).toBe(`/play/${ID}/live`);
    }
  });
});
