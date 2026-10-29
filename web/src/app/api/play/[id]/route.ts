import { forwardToApi, isPlayId } from "@/lib/play-proxy";

export const dynamic = "force-dynamic";

/** Where a game has got to: running, finished (with the game to read) or stopped (with why). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await params;
  if (!isPlayId(id)) return Response.json({ detail: "no such game" }, { status: 404 });
  return forwardToApi(`/play/${id}`, request, "GET");
}
