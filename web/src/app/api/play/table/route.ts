import { forwardToApi, tablePath } from "@/lib/play-proxy";

export const dynamic = "force-dynamic";

/** Deal a table: the eight seats and their roles, and the seed to send back with the cards. */
export function GET(request: Request): Promise<Response> {
  return forwardToApi(tablePath(request.url), request, "GET");
}
