import { forwardToApi } from "@/lib/play-proxy";

export const dynamic = "force-dynamic";

/** Start a game: the four cards go to the API as they are. */
export function POST(request: Request): Promise<Response> {
  return forwardToApi("/play", request, "POST");
}
