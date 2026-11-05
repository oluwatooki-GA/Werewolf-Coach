import { apiBase } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Whether the API is awake. A page that is showing the hand-picked games asks this every few
 * seconds; each ask also keeps the API's start-up going. It answers within a few seconds either
 * way, so the browser never waits for a sleeping API.
 */
export async function GET() {
  let up = false;
  try {
    const response = await fetch(`${apiBase()}/health`, { cache: "no-store", signal: AbortSignal.timeout(4000) });
    up = response.ok;
  } catch {
    // asleep, or on its way up
  }
  return Response.json({ up }, { headers: { "cache-control": "no-store" } });
}
