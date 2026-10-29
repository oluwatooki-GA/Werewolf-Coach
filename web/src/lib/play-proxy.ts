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
