import { forwardToApi } from "@/lib/play-proxy";

export const dynamic = "force-dynamic";

/** The owner's overview: the token travels in the header to the API, which is the one to check it. */
export function GET(request: Request): Promise<Response> {
  const token = request.headers.get("authorization");
  return forwardToApi("/admin/overview", request, "GET", token ? { authorization: token } : {});
}
