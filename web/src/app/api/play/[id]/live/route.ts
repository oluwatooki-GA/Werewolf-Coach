import { forwardToApi, isPlayId, livePath } from "@/lib/play-proxy";

export const dynamic = "force-dynamic";

/** A game being played, as far as it has got: the entries from the point the page last read to. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await params;
  if (!isPlayId(id)) return Response.json({ detail: "no such game" }, { status: 404 });
  return forwardToApi(livePath(id, request.url), request, "GET");
}
