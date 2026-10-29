import { apiBase } from "./api";

/** A play game's id as the API makes it: 32 hex characters, and nothing that could reach another route. */
export function isPlayId(id: string): boolean {
  return /^[0-9a-f]{32}$/.test(id);
}

/**
 * Pass a play request on to the API and give its answer back unchanged, status and message
 * included. The browser talks to the site and never to the API, so the API's address stays on the
 * server; the visitor's address is passed along so the API's rate limit counts visitors, not us.
 */
export async function forwardToApi(path: string, request: Request, method: "GET" | "POST"): Promise<Response> {
  const headers = new Headers({ "content-type": "application/json" });
  const visitor = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (visitor) headers.set("x-forwarded-for", visitor);
  try {
    const upstream = await fetch(`${apiBase()}${path}`, {
      method,
      headers,
      body: method === "POST" ? await request.text() : undefined,
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "The game server is not answering." }, { status: 502 });
  }
}

/** The API path for a table: a seed is passed on only if it is up to six digits, nothing else is. */
export function tablePath(url: string): string {
  const seed = new URL(url).searchParams.get("seed");
  return seed !== null && /^\d{1,6}$/.test(seed) ? `/play/table?seed=${seed}` : "/play/table";
}

/** The API path for a game's live entries: the point to read from is passed on only if it is a number. */
export function livePath(id: string, url: string): string {
  const after = new URL(url).searchParams.get("after");
  return after !== null && /^\d{1,6}$/.test(after) ? `/play/${id}/live?after=${after}` : `/play/${id}/live`;
}
